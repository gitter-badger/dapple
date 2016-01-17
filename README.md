<p align="center">
  <img src="http://ipfs.pics/ipfs/QmPQcPiaep6Bfp956b5xLDaQdtQVtAWBT9QjWNRiL9y8Cw"/>
</p>


`dapple` is a tool for Solidity developers to help build and manage complex contract systems on Ethereum-like blockchains.

#### Installation

[![Join the chat at https://gitter.im/cassiopaia/dapple](https://badges.gitter.im/cassiopaia/dapple.svg)](https://gitter.im/cassiopaia/dapple?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)

Pre 0.2, it is best to install directly from source:

`git clone https://github.com/NexusDevelopment/dapple && cd dapple && npm install -g`

Any stable releases (once they exist) will be available on npm:

`npm install -g dapple`

#### Basic Usage

```
mkdir mydapp && cd mydapp
dapple init

# Write some contracts - see docs for test contract format
vim src/sol/mycontract.sol
vim src/sol/mycontract_test.sol

dapple test # run VM tests
dapple build # export contract definitions, solidity headers, and JS headers (node and browser)
```
