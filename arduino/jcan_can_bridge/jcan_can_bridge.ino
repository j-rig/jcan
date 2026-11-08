// jcan_can_bridge.ino
//
// Bridges an MCP2515-based CAN shield to USB serial using jcan's own
// minimal line protocol, so jcan can talk to it as a CAN interface
// (JCAN_BUS_TYPE=arduino). See README.md in this folder for wiring,
// the required library, and the wire protocol this implements.
//
// Library: "mcp_can" by coryjfowler (install via Arduino Library Manager).

#include <SPI.h>
#include <mcp_can.h>

// Adjust these two to match your shield if CAN.begin() never returns CAN_OK.
const int CAN_CS_PIN = 9;
const byte CAN_CLOCK = MCP_16MHZ;  // common alternative: MCP_8MHZ

const long SERIAL_BAUD = 115200;
const byte CAN_SPEED = CAN_500KBPS;  // standard OBD-II bus speed

MCP_CAN CAN(CAN_CS_PIN);

char lineBuf[64];
uint8_t lineLen = 0;

void setup() {
  Serial.begin(SERIAL_BAUD);
  while (CAN_OK != CAN.begin(MCP_ANY, CAN_SPEED, CAN_CLOCK)) {
    delay(200);
  }
  CAN.setMode(MCP_NORMAL);
}

void loop() {
  pollCanToSerial();
  pollSerialToCan();
}

// Forward any CAN frame received into "R,<id_hex>,<data_hex>\n" on serial.
void pollCanToSerial() {
  if (CAN.checkReceive() != CAN_MSGAVAIL) return;

  long unsigned int id;
  byte len;
  byte buf[8];
  CAN.readMsgBuf(&id, &len, buf);

  Serial.print("R,");
  Serial.print(id, HEX);
  Serial.print(',');
  for (byte i = 0; i < len; i++) {
    printHexByte(buf[i]);
  }
  Serial.print('\n');
}

// Accumulate incoming serial bytes into lines and handle "S,<id_hex>,<data_hex>\n".
void pollSerialToCan() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      lineBuf[lineLen] = '\0';
      handleLine(lineBuf, lineLen);
      lineLen = 0;
    } else if (c != '\r' && lineLen < sizeof(lineBuf) - 1) {
      lineBuf[lineLen++] = c;
    }
  }
}

void handleLine(char *line, uint8_t len) {
  if (len < 2 || line[0] != 'S' || line[1] != ',') return;  // not a send command; ignore

  char *idStr = line + 2;
  char *comma = strchr(idStr, ',');
  if (comma == NULL) return;
  *comma = '\0';
  char *dataStr = comma + 1;

  long unsigned int id = strtoul(idStr, NULL, 16);
  byte data[8];
  byte dataLen = parseHexBytes(dataStr, data, sizeof(data));

  CAN.sendMsgBuf(id, 0, dataLen, data);
}

void printHexByte(byte b) {
  if (b < 0x10) Serial.print('0');
  Serial.print(b, HEX);
}

byte parseHexBytes(const char *hex, byte *out, byte maxLen) {
  byte count = 0;
  while (hex[0] != '\0' && hex[1] != '\0' && count < maxLen) {
    out[count++] = (hexNibble(hex[0]) << 4) | hexNibble(hex[1]);
    hex += 2;
  }
  return count;
}

byte hexNibble(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return 0;
}
