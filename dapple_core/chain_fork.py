import gipc
import json
import os
import random
import signal
import sys
import time
import copy
from uuid import uuid4
from dapple.cli import click, cli
from click import BadParameter
import gevent
from gevent.event import Event
import rlp
from devp2p.service import BaseService
from devp2p.peermanager import PeerManager
from devp2p.discovery import NodeDiscovery
from devp2p.app import BaseApp
from pyethapp.eth_service import ChainService
from pyethapp.console_service import Console
import ethereum.config
import ethereum.slogging as slogging
import pyethapp, pyethapp.config
import pyethapp.db_service
from ethereum import blocks, processblock, utils
from ethereum.chain import Chain
from ethereum.ethpow import get_cache, hashimoto_light, TT64M1
from pyethapp.jsonrpc import JSONRPCServer
from pyethapp.pow_service import Miner, PoWWorker, PoWService
from pyethapp.accounts import AccountsService, Account
from pyethapp.leveldb_service import LevelDB, LevelDBService
from pyethapp.app import EthApp, dump_config, unlock_accounts 
from pyethapp.profiles import PROFILES, DEFAULT_PROFILE
from pyethapp.utils import update_config_from_genesis_json, merge_dict

if sys.version_info.major == 2:
    from repoze.lru import lru_cache
else:
    from functools import lru_cache

log = slogging.get_logger('app')
log_sub = slogging.get_logger('fake_pow.subprocess')

default_data_dir = click.get_app_dir('dapple')


class EphemeralLevelDB(LevelDB):
    def commit(*args, **kwargs):
        pass


class FakePoWService(PoWService):
    difficulty = 0

    def __init__(self, app):
        super(FakePoWService, self).__init__(app)
        cpu_pct = self.app.config['pow']['cpu_pct']
        self.cpipe, self.ppipe = gipc.pipe(duplex=True)
        self.worker_process = gipc.start_process(
            target=fake_powworker_process, args=(self.cpipe, cpu_pct))
        self.app.services.chain.on_new_head_candidate_cbs.append(self.on_new_head_candidate)
        self.hashrate = 0

    def recv_found_nonce(self, bin_nonce, mixhash, mining_hash):
        log.info('nonce found', mining_hash=mining_hash.encode('hex'))
        blk = self.app.services.chain.chain.head_candidate
        blk.mixhash = mixhash
        blk.nonce = bin_nonce
        self.app.services.chain.add_mined_block(blk)


class FakePoWWorker(PoWWorker):
    def recv_mine(self, mining_hash, block_number, difficulty):
        "restarts the miner"
        log_sub.debug('received new mining task', difficulty=difficulty)
        assert isinstance(block_number, int)
        if self.miner:
            self.miner.stop()
        self.miner = FakeMiner(mining_hash, block_number, difficulty,
                self.send_found_nonce, self.send_hashrate, self.cpu_pct)
        self.miner.start()


class FakeMiner(Miner):
    def _run(self):
        cache = get_cache(self.block_number)
        nonce = random.randint(0, TT64M1)

        # TODO: Make the mining delay configurable.
        gevent.sleep(1)

        log_sub.trace('starting mining round')
        bin_nonce = utils.zpad(utils.int_to_big_endian(nonce & TT64M1), 8)
        mix_hash = hashimoto_light(self.block_number, cache,
                self.mining_hash, bin_nonce)["mix digest"]
        log_sub.info('nonce found')
        self.nonce_callback(bin_nonce, mix_hash, self.mining_hash)

        log_sub.debug('mining task finished', is_stopped=self.is_stopped)


class ChainWrapper(object):
    def __init__(self, chain):
        self.__dict__['_wrapped_chain'] = chain

    def add_block(self, block, forward_pending_transactions=True):
        "returns True if block was added sucessfully"
        _log = log.bind(block_hash=block)
        # make sure we know the parent
        if not block.has_parent() and not block.is_genesis():
            _log.debug('missing parent')
            return False

        if not block.validate_uncles():
            _log.debug('invalid uncles')
            return False

        if block.number < self.head.number:
            _log.debug("older than head", head_hash=self.head)
            # Q: Should we have any limitations on adding blocks?

        self.index.add_block(block)
        self._store_block(block)

        # set to head if this makes the longest chain w/ most work for that number
        if block.chain_difficulty() > self.head.chain_difficulty():
            _log.debug('new head')
            self._update_head(block, forward_pending_transactions)
        elif block.number > self.head.number:
            _log.warn('has higher blk number than head but lower chain_difficulty',
                      head_hash=self.head, block_difficulty=block.chain_difficulty(),
                      head_difficulty=self.head.chain_difficulty())
        block.transactions.clear_all()
        block.receipts.clear_all()
        block.state.db.commit_refcount_changes(block.number)
        block.state.db.cleanup(block.number)
        self.commit()  # batch commits all changes that came with the new block
        return True

    def __getattr__(self, attr):
        return getattr(self._wrapped_chain, attr)

    def __setattr__(self, attr, value):
        return setattr(self._wrapped_chain, attr, value)

    def __delattr__(self, attr):
        self._wrapped_chain.__delattr__(attr)


class FakeChainService(ChainService):
    def __init__(self, *args, **kwargs):
        super(FakeChainService, self).__init__(*args, **kwargs)
        self.chain = ChainWrapper(self.chain)

    def add_mined_block(self, block):
        log.debug('adding mined block', block=block)
        assert isinstance(block, blocks.Block)
        if self.chain.add_block(block):
            log.debug('added', block=block, ts=time.time())
            assert block == self.chain.head
            self.broadcast_newblock(block, chain_difficulty=block.chain_difficulty())


def fake_powworker_process(cpipe, cpu_pct):
    gevent.get_hub().SYSTEM_ERROR = BaseException  # stop on any exception
    FakePoWWorker(cpipe, cpu_pct).run()


class EphemeralLevelDBService(EphemeralLevelDB, BaseService):
    name = 'db'
    default_config = dict(data_dir='')

    def __init__(self, app):
        BaseService.__init__(self, app)
        assert self.app.config['data_dir']
        self.uncommitted = dict()
        self.stop_event = Event()
        dbfile = os.path.join(self.app.config['data_dir'], 'leveldb')
        EphemeralLevelDB.__init__(self, dbfile)

    def _run(self):
        self.stop_event.wait()

    def stop(self):
        self.stop_event.set()


@cli.group(name='chain')
def cli_chain():
    pass


@cli_chain.command(name='sync')
@click.option('-e', '--env', default=DEFAULT_PROFILE)
@click.pass_context
def sync(ctx, env):
    services = [pyethapp.db_service.DBService, AccountsService, NodeDiscovery,
            PeerManager, ChainService, JSONRPCServer, Console]

    pyethapp.config.setup_data_dir(default_data_dir)
    config = pyethapp.config.load_config(default_data_dir)
    config['data_dir'] = default_data_dir
    pyethapp.config.update_config_with_defaults(
        config, pyethapp.config.get_default_config([EthApp] + services))
    pyethapp.config.update_config_with_defaults(
        config, {'eth': {'block': blocks.default_config}})
    merge_dict(config, PROFILES[env])
    update_config_from_genesis_json(config, config['eth']['genesis'])

    app = EthApp(config)
    dump_config(config)

    for service in services:
        assert issubclass(service, BaseService)
        if service.name not in app.config['deactivated_services']:
            assert service.name not in app.services
            service.register_with_app(app)
            assert hasattr(app.services, service.name)

    log.info('starting')
    app.start()

    if config['post_app_start_callback'] is not None:
        config['post_app_start_callback'](app)

    # wait for interrupt
    evt = Event()
    gevent.signal(signal.SIGQUIT, evt.set)
    gevent.signal(signal.SIGTERM, evt.set)
    gevent.signal(signal.SIGINT, evt.set)
    evt.wait()

    # finally stop
    app.stop()


@cli_chain.command()
@click.option('-u', '--unlock', multiple=True, type=str)
def fake(env=DEFAULT_PROFILE, unlock=[]):
    blocks.BlockHeader.check_pow = lambda *args: True
    services = [pyethapp.db_service.DBService, AccountsService, NodeDiscovery,
            PeerManager, FakeChainService, FakePoWService, JSONRPCServer,
            Console]

    slogging.configure(':info', log_json=False)
    config = pyethapp.config.load_config(default_data_dir)
    config['data_dir'] = default_data_dir
    pyethapp.config.update_config_with_defaults(
        config, pyethapp.config.get_default_config([EthApp] + services))
    pyethapp.config.update_config_with_defaults(
        config, {'eth': {'block': blocks.default_config}})
    merge_dict(config, PROFILES[env])
    update_config_from_genesis_json(config, config['eth']['genesis'])

    # Mine minimally.
    config['pow']['activated'] = True
    config['pow']['cpu_pct'] = 1

    # Connect to nobody.
    config['discovery']['bootstrap_nodes'] = []
    config['discovery']['listen_port'] = 29873
    config['p2p']['listen_port'] = 29873
    config['p2p']['min_peers'] = 0

    # Fake the difficulty.
    blocks.GENESIS_DIFFICULTY = 1024
    blocks.BLOCK_DIFF_FACTOR = 16
    blocks.MIN_GAS_LIMIT = blocks.default_config['GENESIS_GAS_LIMIT'] / 2

    app = EthApp(config)
    dump_config(config)

    pyethapp.db_service.dbs['EphemeralLevelDB'] = EphemeralLevelDBService
    app.config['db']['implementation'] = 'EphemeralLevelDB'
    
    # register services
    for service in services:
        assert issubclass(service, BaseService)
        if service.name not in app.config['deactivated_services']:
            assert service.name not in app.services
            service.register_with_app(app)
            assert hasattr(app.services, service.name)

    if ChainService.name not in app.services:
        log.fatal('No chainmanager registered')
        ctx.abort()

    if pyethapp.db_service.DBService.name not in app.services:
        log.fatal('No db registered')
        ctx.abort()

    unlock_accounts(unlock, app.services.accounts)

    # start app
    log.info('Starting %s chain...' % env)
    app.start()

    if 'peermanager' in app.services:
        app.services.peermanager.stop()

    # wait for interrupt
    evt = Event()
    gevent.signal(signal.SIGQUIT, evt.set)
    gevent.signal(signal.SIGTERM, evt.set)
    gevent.signal(signal.SIGINT, evt.set)
    evt.wait()

    # finally stop
    app.stop()
