import numpy as np
import fractions
def convert_24bit_to_32bit(byte):
    byte_array = bytearray(byte)
    if len(byte_array) % 3 != 0:
        raise ValueError("Byte array length must be a multiple of 3 (24 bits per value)")

    # Initialize an empty list to store the 32-bit values
    int32_values = []

    # Iterate over the byte array, reading 3 bytes (24 bits) at a time
    for i in range(0, len(byte_array), 3):
        # Convert 24-bit value to a 32-bit integer
        value = byte_array[i] << 16 | byte_array[i + 1] << 8 | byte_array[i + 2]
        # If the most significant bit is set, it's a negative value, so we need to sign-extend
        if value & 0x800000:
            value |= ~0xFFFFFF
        fraction = fractions.Fraction(value, 2*24-1)
        int32_value = fraction * 2*32-1
        int32_values.append(int32_value)

    ret = np.array(int32_values, dtype=np.int32)
    return bytes(ret)