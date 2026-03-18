import struct

def create_test_dflash(filename="test_dflash.bin"):
    nb_blocks = 128
    block_size = 256
    dflash = bytearray([0xFF] * (nb_blocks * block_size))

    BLOCK_VALID = 0xFACF
    CMD_VALID = 0xB800

    # EEPROM image (4KB) - we simulate it here first then convert to dflash commands
    eee = bytearray([0xFF] * 4096)

    # 1. Setup VIN (at 0xFD3, 17 bytes)
    vin_data = b"WBAAA0000TEST1234" # 17 chars
    eee[0xFD3:0xFD3+17] = vin_data

    # 2. Setup Production Date (0xFBB: Year[2], 0xFBD: Month, 0xFBE: Day)
    # Target: 02.03.2024
    eee[0xFBB] = 0x20
    eee[0xFBC] = 0x24
    eee[0xFBD] = 0x03
    eee[0xFBE] = 0x02

    # 3. Add more dummy data to pass MIN_WORDS (16) check
    # We need at least 16 words. VIN(9) + Date(2) = 11.
    # Add 10 more dummy words at 0x100
    for i in range(10):
        eee[0x100 + i*2] = 0xAA
        eee[0x100 + i*2 + 1] = 0x55

    # 4. Setup FA (Vehicle Order) - Simplified simulation
    # FA starts at 0x04. dflash_to_eee reads 0x140 bytes.
    # It's 6-bit encoded, very complex. We'll just put some valid-looking bits there.
    # To get "E90", etc.
    # For now, let's just focus on getting a non-empty string if possible, 
    # but the 6-bit decoding is sensitive. I'll just skip complex FA for this test.

    # 4. Convert EEE bytearray to D-Flash commands
    # Each command updates one 16-bit WORD.
    cmd_count = 0
    block_id = 0
    # Write block header
    struct.pack_into(">HH", dflash, block_id * block_size, BLOCK_VALID, 0x0001)
    
    for addr_word in range(2048):
        # Only write non-empty words
        val = (eee[addr_word*2] << 8) | eee[addr_word*2 + 1]
        if val != 0xFFFF:
            # Command format: (addr | 0xB800) [2 bytes] + data [2 bytes]
            offset = (block_id * block_size) + 4 + (cmd_count * 4)
            cmd_header = (addr_word & 0x07FF) | CMD_VALID
            struct.pack_into(">HH", dflash, offset, cmd_header, val)
            cmd_count += 1
            
            if cmd_count >= 63: # Block full
                block_id += 1
                cmd_count = 0
                struct.pack_into(">HH", dflash, block_id * block_size, BLOCK_VALID, 0x0001)

    # Set the "End of Cycle" indicator at the last block
    struct.pack_into(">HH", dflash, 127 * block_size, 0xFFFF, 0xFFFE)

    with open(filename, "wb") as f:
        f.write(dflash)
    print(f"Created {filename} with corrected alignment.")

if __name__ == "__main__":
    create_test_dflash()
