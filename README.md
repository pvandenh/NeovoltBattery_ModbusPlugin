# Neovolt Inverter Integration for Home Assistant

A Home Assistant custom integration for Neovolt/Bytewatt inverters and battery systems using Modbus TCP protocol.

<img width="225" height="80" alt="image" src="https://github.com/user-attachments/assets/fd21d47f-ff23-44cb-bd60-02c9f13d0f06" />

---

## ⚠️ Upgrading to v2 release from v1

This update significantly changes the battery control model. The previous multi-entity charge/discharge controls have been replaced by a single **Dispatch Mode** selector with supporting number entities. Any automations referencing the old control entities will need to be updated. If you need to keep the previous behaviour temporarily, stay on v1.0.8 — however, no further development will occur on that version.

---

## 🎯 What Does This Integration Do?

This integration connects your Neovolt inverter to Home Assistant, giving you:

- **Real-time monitoring** of solar production, battery status, and grid usage
- **Full battery control** via a single Dispatch Mode selector
- **Dynamic Export and Dynamic Import modes** for automatic grid power management
- **Energy tracking** for the Home Assistant Energy Dashboard
- **Multi-inverter support** with combined sensors for parallel setups
- **Automations** to optimise when your battery charges and discharges

---

## 📋 What You Need

### Hardware
- Neovolt/Bytewatt inverter (battery or hybrid)
- One of: direct Ethernet/Modbus TCP port on the inverter, or an EW11A WiFi RS485 adapter
- Home Assistant installed and running

### Software
- Home Assistant 2025.1 or newer
- HACS (Home Assistant Community Store)
- pymodbus 3.10.0 or higher (installed automatically)

**Don't have HACS?** Install it first: https://hacs.xyz/docs/setup/download

---

## 📦 Installation

### Step 1: Choose Your Connection Method

| Connection Type | When to Use | Pros | Cons |
|----------------|-------------|------|------|
| **Direct Ethernet** | Inverter has built-in Ethernet/Modbus TCP port | Simple, no extra hardware, most reliable | Requires network access near inverter |
| **EW11A WiFi Adapter** | Inverter has RS485 port only | Wireless, flexible placement | Extra hardware, requires configuration |

#### Option A: Direct Ethernet

1. Plug an Ethernet cable into the inverter's Modbus TCP port and connect to your network.
2. Find the inverter's IP address in your router's device list and note it down.
3. Reserve a static IP for it in your router's DHCP settings.
4. Default settings are: **Port 502**, **Slave ID 85** — no changes needed.

#### Option B: EW11A WiFi Adapter

📥 **Full setup guide**: [Neovolt_Modbus initial hardware setup.docx](https://github.com/pvandenh/NeovoltBattery_ModbusPlugin/blob/main/custom_components/neovolt/Neovolt_Modbus%20initial%20hardware%20setup.docx)

Quick summary:
1. Wire the EW11A to your inverter's RS485 port.
2. Connect EW11A to your WiFi network.
3. Configure serial settings: **9600 baud, Modbus protocol**.
4. Configure network settings: **TCP Server, Port 502**.
5. Assign a static IP to the EW11A in your router.

---

### Step 2: Add via HACS

1. Open **HACS** in the Home Assistant sidebar.
2. Click the **⋮ menu** → **Custom repositories**.
3. Add repository: `https://github.com/pvandenh/NeovoltBattery_ModbusPlugin`, category: **Integration**.
4. Search for **Neovolt** and click **Download**.
5. **Restart Home Assistant**.

---

### Step 3: Add the Integration

1. Go to **Settings → Devices & Services → + Add Integration**.
2. Search for **Neovolt Solar Inverter** and select it.

---

### Step 4: Configure Connection

| Setting | Description | Default |
|---------|-------------|---------|
| **Host (IP Address)** | IP of your inverter or EW11A gateway | — |
| **Port** | Modbus TCP port | `502` |
| **Slave ID** | Modbus slave address | `85` |
| **Device Name** | Optional friendly name (leave blank for auto-numbering) | — |
| **Device Role** | Host = full control; Follower = sensors only | `Host` |

---

### Step 5: Configure Power Limits (Host devices only)

| Setting | Description | Example |
|---------|-------------|---------|
| **Max Charge Power (kW)** | Maximum charging power | `5.0` single / `15.0` for 3× 5kW |
| **Max Discharge Power (kW)** | Maximum discharging power | `5.0` single / `15.0` for 3× 5kW |

For parallel/master-slave setups enter the **total combined capacity**.

---

### Step 6: Configure Polling & Recovery (Optional)

| Setting | Default | Description |
|---------|---------|-------------|
| **Min Poll Interval** | 10 s | Fastest polling rate (hard minimum 10 s) |
| **Max Poll Interval** | 300 s | Slowest polling rate for stable values |
| **Recovery: Consecutive Failures** | 5 | Auto-reconnect after this many failures |
| **Recovery: Data Staleness** | 10 min | Auto-reconnect if no data changes |

Most users can leave these at defaults.

---

## ✨ Features

### 📊 Monitoring Sensors

**Grid**
- Grid voltage, current, and power (3-phase)
- Grid frequency and power factor
- Total energy imported and exported

**Solar**
- PV voltage, current, and power per string (PV1, PV2, PV3)
- Total PV power (DC + AC combined)
- Total and daily PV energy (daily resets at midnight)

**Battery**
- Voltage, current, power (charge/discharge)
- State of Charge (SOC %) and State of Health (SOH %)
- Min/max cell voltages and temperatures
- Battery capacity, total charge/discharge energy
- Battery status (Idle / Charging / Discharging)
- Battery relay status
- Battery warning, fault, and protection flags

**Inverter**
- Inverter temperatures (multiple zones)
- Bus voltage, active power, backup power
- Energy input/output totals
- Inverter work mode (Wait / Normal / Fault / etc.)
- Inverter warning and fault flags (full bit-mapped decode)
- System fault register (network card, BMS, parallel comms, etc.)

**Calculated**
- House load (PV + Battery + Grid)
- Dispatch Status (shows active mode, power, remaining duration, any warnings)
- Grid Power Offset (calibration, when supported by firmware)

**Combined sensors (Host device, dual-inverter setups only)**

When a Follower device is also configured, the Host automatically exposes aggregate sensors covering both inverters:
- Combined Battery Power
- Combined Battery SOC (capacity-weighted average)
- Combined Battery SOH (capacity-weighted average)
- Combined Battery Capacity
- Combined House Load
- Combined PV Power
- Combined Battery Min/Max Cell Voltage
- Combined Battery Min/Max Cell Temperature
- Combined Battery Charge/Discharge Energy

---

### 🎛️ Battery Control

All battery control flows through a single **Dispatch Mode** selector. Configure the supporting number entities first, then select a mode.

#### Dispatch Mode (Select Entity)

| Mode | Description |
|------|-------------|
| **Normal** | Battery operates automatically based on inverter configuration |
| **Force Charge** | Charges from solar/grid at the configured power until the target SOC is reached |
| **Force Discharge** | Discharges to load/grid at the configured power until the cutoff SOC is reached |
| **Dynamic Export** | Continuously adjusts discharge to maintain grid export at the target level |
| **Dynamic Import** | Continuously adjusts charging to maintain grid import at the target level |
| **No Battery Charge** | Prevents all battery charging (from solar and grid). Will still discharge to loads if needed |
| **Idle (No Dispatch)** | Halts all battery dispatch (charging + discharging) — inverter stays online but battery sits idle |

> **Note:** Selecting **Normal** or pressing the **Stop Force Charge/Discharge** button cancels any active dispatch mode.

#### Dispatch Configuration (Number Entities)

Set these before activating Force Charge, Force Discharge, or Dynamic modes.

| Entity | Range | Description |
|--------|-------|-------------|
| **Dispatch Power** | 0.5 – max kW | Charge or discharge power (slider max reflects your configured system capacity) |
| **Dispatch Duration** | 1 – 480 min | How long to run the dispatch command |
| **Dispatch Charge Target SOC** | 10 – 100 % | Stop Force Charge when battery reaches this SOC |
| **Dispatch Discharge Cutoff SOC** | 4 – 100 % | Stop Force Discharge when battery falls to this SOC |
| **Dynamic Mode Power Target** | 0.05 – 15 kW | Target export power (Dynamic Export) or target import power (Dynamic Import) |

#### How to Use Force Charge

1. Set **Dispatch Power** to the desired charge rate (e.g. 4 kW).
2. Set **Dispatch Duration** (e.g. 120 minutes).
3. Set **Dispatch Charge Target SOC** to your desired ceiling (e.g. 100 %).
4. Set **Dispatch Mode** → **Force Charge**.

The battery will charge at the specified rate until either the duration expires or the target SOC is reached.

#### How to Use Dynamic Export

Dynamic Export discharges the battery to keep grid export at a constant target level, accounting for varying house load. It re-evaluates every 10 seconds.

1. Set **Dynamic Mode Power Target** to your desired export level in kW (e.g. 5kW to the grid).
2. Set **Dispatch Mode** → **Dynamic Export**.

The integration will automatically adjust discharge power every 10 seconds, with a 0.3 kW debounce to avoid excessive commands.

#### How to Use Dynamic Import

Dynamic Import charges the battery from the grid while holding a target import level. Useful for off-peak tariff charging without overloading the connection.

1. Set **Dynamic Mode Power Target** to the grid import power you want to maintain (e.g. 2 kW).
2. Set **Dispatch Mode** → **Dynamic Import**.

#### Additional Controls

| Entity | Description |
|--------|-------------|
| **PV Switch** (Select) | Control PV input: Auto / Open / Close |
| **Time Period Control** (Select) | Enable or disable time-based charge/discharge schedules programmed on the inverter | *Note - currently not working*
| **Stop Force Charge/Discharge** (Button) | Immediately cancels all active dispatch (including dynamic modes) and returns to Normal |

---

### ⚙️ System Settings (Number Entities)

| Entity | Range | Register | Description |
|--------|-------|----------|-------------|
| **Max Feed to Grid Power** | 0 – 100 % | 0x0800 | Cap on grid export as a percentage of rated power |
| **Charging Cutoff SOC** | 10 – 100 % | 0x0855 | Maximum SOC the battery will charge to under normal (automatic) operation |
| **Discharging Cutoff SOC (Default)** | 4 – 100 % | 0x0850 | Minimum SOC the battery will discharge to under normal operation |
| **PV Capacity** | 0 – max W | 0x0801 | Total installed PV capacity in Watts (32-bit register) |
| **Grid Power Offset** | −500 – +500 W | 0x11D5 | Signed calibration offset for the grid power reading. Positive values bias toward export/discharge; negative values toward import. Only visible when the firmware exposes this register. |

---

## 🔄 Multi-Inverter Setup (Parallel / Master-Slave)

### Recommended configuration

1. **Host device** (your master/primary inverter)
   - Device Role: **Host**
   - Set Max Charge/Discharge Power to the **total combined capacity** (e.g. 15 kW for 3 × 5 kW)
   - All control and combined sensor entities appear here

2. **Follower device(s)** (secondary inverters)
   - Device Role: **Follower**
   - Sensor-only — no control entities are created
   - Combined sensors on the Host automatically include follower data once linked

The integration links Host and Follower coordinators automatically after both entries load, regardless of load order. Combined sensors appear on the Host device and aggregate data from both inverters.

---

## ⚙️ Changing Settings After Installation

1. Go to **Settings → Devices & Services**.
2. Find **Neovolt Inverter**, click **⋮ → Configure**.
3. Step through: Device Role → Power Limits → Polling & Recovery.
4. Click **Submit** — the integration will reload with your new settings.

---

## 🔌 Connection Troubleshooting

### Direct Ethernet

- Can't find IP: check router device list, use the Fing app, or check the inverter's display.
- Connection refused on port 502: verify Modbus TCP is enabled on the inverter and that port 502 isn't blocked.
- Intermittent connection: assign a static IP in your router's DHCP reservation.

### EW11A

- Can't connect to EW11A hotspot: wait 30 s after power-on; look for a network starting with "EW11".
- EW11A not on home network: verify WiFi credentials, confirm STA mode, and check the router's device list.
- Data errors: verify serial settings are 9600 baud and TCP Server is enabled on port 502.

Full EW11A guide: [Neovolt_Modbus initial hardware setup.docx](https://github.com/pvandenh/NeovoltBattery_ModbusPlugin/blob/main/custom_components/neovolt/Neovolt_Modbus%20initial%20hardware%20setup.docx)

---

## ❓ Common Problems

### "Cannot Connect" Error

- Verify the inverter/gateway is powered on and the IP is correct.
- Ping the IP from the Home Assistant Terminal: `ping <IP>`
- Check port 502 is reachable: `telnet <IP> 502`
- Check Home Assistant logs for the detailed error.

### Sensors Show "Unavailable"

- Confirm Slave ID is correct (default: 85).
- Wait a few minutes for the initial poll to complete.
- Reload the integration: Settings → Devices & Services → Neovolt → ⋮ → Reload.
- Enable debug logging and check logs (see below).

### Force Charge / Discharge Not Working

- Check battery SOC is within the allowed range for the chosen mode.
- Confirm the dispatch power is at least 0.5 kW.
- Press **Stop Force Charge/Discharge** first to clear any stuck state, then re-apply.
- Check the **Dispatch Status** sensor for error messages.

### Battery Not Reaching 100 % SOC

This was a bug in earlier versions (SOC register used 0–250 instead of 0–255). It is fixed in v2.0.0. Update to the latest version and ensure **Dispatch Charge Target SOC** is set to 100 %.

### Power Sliders Are Limited

The dispatch power slider maximum is derived from your configured Max Charge/Discharge Power. If you have multiple inverters, update those values via **Configure** (see above).

### Stale Data Warning

The `data_stale` attribute on sensors indicates the integration is using cached data due to a connection issue. Auto-recovery will reconnect automatically. Sensors remain available for up to 12 hours on cached data before becoming unavailable.

---

## 📝 Enable Debug Logging

Add to `/config/configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.neovolt: debug
    pymodbus: debug
```

Restart Home Assistant, then check **Settings → System → Logs** and search for `neovolt`.

---

## 🔧 Advanced: Optimising Polling

The integration uses adaptive polling — intervals automatically speed up for changing values and slow down for stable ones.

**Slower/less reliable networks:**
```
Min Poll Interval: 15 s
Max Poll Interval: 600 s
Consecutive Failures: 10
Staleness Threshold: 20 min
```

**Fast, reliable networks:**
```
Min Poll Interval: 10 s
Max Poll Interval: 120 s
Consecutive Failures: 3
Staleness Threshold: 5 min
```

---

## 📱 Getting Help

1. Check logs first: Settings → System → Logs (search `neovolt`).
2. Search existing issues: https://github.com/pvandenh/NeovoltBattery_ModbusPlugin/issues
3. Open a new issue and include:
   - Home Assistant version
   - Integration version (from HACS)
   - Connection type (Direct Ethernet or EW11A)
   - Device role configuration
   - Log output with debug logging enabled
   - Steps already tried

---

## 🌟 Contributing

Pull requests are welcome! Areas for contribution: bug fixes, new features, documentation improvements.

---

## 📄 License

MIT License — free to use, modify, and share.

---

## 👍 Credits

- Based on Bytewatt Modbus RTU Protocol V1.12
- Developed for the Home Assistant community
- Development assistance from Claude.ai
- Thanks to all contributors and testers

---

*For Modbus protocol details and advanced features, see the repository source code and inline documentation.*
