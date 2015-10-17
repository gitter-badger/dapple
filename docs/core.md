# Core Package

By default, Dapple adds a dependency on a package called `core` to all new Dapple packages. This package provides simple contracts that can be extended to take advantage of some of Dapple's features.

## core/debug.sol

### contract Debug

This contract provides events that produce logging output during testing. (I.e., when running `dapple test`.)

#### logs(bytes value)

Logs a `string` or a `bytes` value (which is then interpreted as a string).

#### log_bool(bool value)

Logs a boolean value.

#### log_named_bool(bytes32 extra_data, bool value)

Logs a boolean value along with a 32-byte string.

#### log_uint(uint value)

Logs an unsigned integer value.

#### log_named_uint(bytes32 extra_data, uint value)

Logs an unsigned integer value along with a 32-byte string.

#### log_int(int value)

Logs an integer value.

#### log_named_int(bytes32 extra_data, int value)

Logs an integer value along with a 32-byte string.

#### log_address(address value)

Logs an address.

#### log_named_address(bytes32 extra_data, address value)

Logs an address value along with a 32-byte string.

#### log_bytes(bytes value)

Logs a `bytes` value.

#### log_named_bytes(bytes32 extra_data, bytes value)

Logs a `bytes` value along with a 32-byte string.

#### log_bytes\[1..32\](bytes[1..32] value)

This entry is for the 32 logging functions numbered consecutively from `log_bytes1` to `log_bytes32`. Each logs a value consisting of the specified number of bytes.

#### log_named_bytes\[1..32\](bytes32 extra_data, bytes[1..32] value)

This entry is for the 32 logging functions numbered consecutively from `log_named_bytes1` to `log_named_bytes32`. Each logs a value consisting of the specified number of bytes, along with a 32-byte string.

#### String formatting

Dapple supports combining the output of multiple log events via `%s`. For example, this code:

```
logs("%s + %s = %s");
log_uint(2);
log_uint(2);
log_uint(4);
```

produces this output:

```
2 + 2 = 4
```

## core/test.sol

### contract Test is Debug

Test contracts must inherit from this contract. It provides some basic assertion-related functions in addition to the events defined in its `Debug` parent type.

#### fail()

Immediately fail the test.

#### assertTrue(bool value[, bytes32 error_message])

Fails the test if `value` is `false`. If `error_message` is provided, includes it in the logging output upon failure. 

#### assertFalse(bool value[, bytes32 error_message])

Fails the test if `value` is `true`. If `error_message` is provided, includes it in the logging output upon failure. 

#### assertEq0(bytes value_1, bytes value_2, bytes32 error_message)

Fails the test if the two `bytes` values are not equal. (Has to be equal in both length and value to pass.)

#### assertEq\[1..32\](bytes[1..32] value_1, bytes[1..32] value_2[, bytes32 error_message])

This entry is for the 32 functions defined for comparing specific byte-length types, numbered consecutively from `assertEq1` to `assertEq32`. Fails the test if the two values are not equal and optionally takes an error message to show upon failure.

#### assertEq(uint value_1, uint value_2[, bytes32 error_message])

Fails the test if the two unsigned integers are not equal. Optionally takes a bytes-32 error message to log if the test fails.

#### assertEq(int value_1, int value_2[, bytes32 error_message])

Fails the test if the two integers are not equal. Optionally takes a bytes-32 error message to log if the test fails.

#### assertEq(bool value_1, bool value_2[, bytes32 error_message])

Fails the test if the two booleans are not equal. Optionally takes a bytes-32 error message to log if the test fails.

#### assertEq(address value_1, address value_2[, bytes32 error_message])

Fails the test if the two addresses are not equal. Optionally takes a bytes-32 error message to log if the test fails.
