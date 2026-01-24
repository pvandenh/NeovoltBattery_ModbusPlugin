# Neovolt Inverter Integration for Home Assistant

A Home Assistant custom integration for Neovolt/Bytewatt inverters and battery systems using Modbus TCP protocol.

<img width="225" height="80" alt="image" src="https://github.com/user-attachments/assets/fd21d47f-ff23-44cb-bd60-02c9f13d0f06" />



# *** Important info for updating to version 2.0.0
Note: This update changes the available controls for charging/discharging, so any existing related custom automations will need to be checked and updated accordingly. If you wish to retain the previous settings temporarily, it is best to remain on version 1.0.8, but note there will be no further development on the old version.



## 🎯 What Does This Integration Do?

This integration connects your Neovolt inverter to Home Assistant, giving you:
- **Real-time monitoring** of your solar production, battery status, and grid usage
- **Full control** over battery charging and discharging
- **Energy tracking** for the Home Assistant Energy Dashboard
- **Automations** to optimize when your battery charges and discharges

Perfect for monitoring your battery system and creating smart automations to save money on electricity!

---

## 📋 What You Need

### Hardware
- ✅ Neovolt/Bytewatt inverter (battery or hybrid inverter)
- ✅ **One of these connection options**:
  - **Option A**: Direct Ethernet cable (if your inverter has Ethernet/Modbus TCP port)
  - **Option B**: EW11A WiFi RS485 adapter (converts RS485 to WiFi/Ethernet)
- ✅ Home Assistant installed and running

### Software
- ✅ Home Assistant 2025.1 or newer
- ✅ HACS (Home Assistant Community Store) installed
- ✅ pymodbus version 3.10.0 or higher

**Don't have HACS?** Install it first: https://hacs.xyz/docs/setup/download

---

## 📦 Installation

### Prep: Choose Your Connection Method

**Which connection method should I use?**

| Connection Type | When to Use | Pros | Cons |
|----------------|-------------|------|------|
| **Direct Ethernet** | Your inverter has built-in Ethernet/Modbus TCP port | ✅ Simple wiring<br>✅ No extra hardware<br>✅ Most reliable | ❌ Requires network access near inverter |
| **EW11A WiFi Adapter** | Your inverter only has RS485 port | ✅ Wireless connection<br>✅ Flexible placement | ❌ Extra hardware needed<br>❌ Requires configuration |

### Hardware Setup - Option A: Direct Ethernet Connection

If your Neovolt inverter has a built-in Ethernet port with Modbus TCP support:

1. **Connect Ethernet Cable**
   - Plug an Ethernet cable directly into your inverter's Modbus TCP port
   - Connect the other end to your network (router/switch)

2. **Find the Inverter's IP Address**
   - Check your router's device list
   - Look for a device named similar to "Neovolt" or "Bytewatt"
   - Note down the IP address (e.g., `192.168.2.125`)

3. **Assign Static IP (Recommended)**
   - In your router's DHCP settings, reserve this IP address for the inverter
   - This prevents the IP from changing

4. **Verify Connection**
   - The inverter should already be configured for:
     - **Port**: 502 (Modbus TCP standard)
     - **Slave ID**: 85 (Neovolt default)
   - Test by pinging the IP from Home Assistant Terminal:
     ```
     ping 192.168.2.125
     ```

**You're ready to install the integration! Skip to "Step 1: Add Custom Repository to HACS" below.**

---

### Hardware Setup - Option B: EW11A WiFi Adapter

If your inverter only has RS485 ports, follow this detailed guide:

📥 **Download Full Setup Guide**: [Neovolt_Modbus initial hardware setup.docx](https://github.com/pvandenh/NeovoltBattery_ModbusPlugin/blob/main/custom_components/neovolt/Neovolt_Modbus%20initial%20hardware%20setup.docx)

**Quick Overview:**

1. **Wire the EW11A adapter** to your inverter's RS485 port using the supplied cables
2. **Connect EW11A to WiFi** - Configure it to join your home network
3. **Configure Serial Settings**:
   - Baud rate: 9600
   - Protocol: Modbus
4. **Configure Network Settings**:
   - Protocol: TCP Server
   - Port: 502
5. **Assign Static IP** to the EW11A in your router

For detailed wiring diagrams and step-by-step instructions, download the complete setup guide linked above.

---

### Step 1: Add Custom Repository to HACS

1. Open Home Assistant
2. Go to **HACS** (in the sidebar)
3. Click the **three dots** (⋮) in the top right corner
4. Select **Custom repositories**
5. Add this information:
   - **Repository**: `https://github.com/pvandenh/NeovoltBattery_ModbusPlugin`
   - **Category**: Select **Integration**
6. Click **ADD**

### Step 2: Install the Integration

1. In HACS, click **Integrations**
2. Click the **+ EXPLORE & DOWNLOAD REPOSITORIES** button
3. Search for **"Neovolt"**
4. Click on **Neovolt Inverter**
5. Click **DOWNLOAD**
6. Click **DOWNLOAD** again to confirm
7. **Restart Home Assistant**
   - Go to **Settings** → **System** → **Restart**

### Step 3: Add the Integration

1. After Home Assistant restarts, go to **Settings** → **Devices & Services**
2. Click **+ ADD INTEGRATION** (bottom right)
3. Search for **"Neovolt"**
4. Click on **Neovolt Solar Inverter**

### Step 4: Configure Connection

You'll need to enter these details:

| Setting | What to Enter | Example |
|---------|---------------|---------|
| **Host (IP Address)** | IP address of your inverter or EW11A | **Direct**: `192.168.2.125`<br>**EW11A**: `192.168.1.100` |
| **Port** | Leave as default | `502` |
| **Slave ID** | Leave as default | `85` |
| **Device Name** | Optional friendly name | Leave empty for auto-numbering |
| **Device Role** | Host or Follower | **Host** (full control)<br>**Follower** (read-only) |

### Step 5: Configure Power Limits (Host Devices Only)

| Setting | What to Enter | Example |
|---------|---------------|---------|
| **Max Charge Power** | Maximum charging power in kW | `5.0` (single inverter)<br>`15.0` (three inverters) |
| **Max Discharge Power** | Maximum discharging power in kW | `5.0` (single inverter)<br>`15.0` (three inverters) |

**Multiple Inverters?**
If you have a parallel/master-slave setup, enter the **total combined capacity**. For example, three 5kW inverters = 15kW total.

### Step 6: Configure Polling & Recovery (Optional)

Advanced settings for adaptive polling and auto-recovery:

| Setting | Default | Description |
|---------|---------|-------------|
| **Min Poll Interval** | 10 seconds | Fastest polling for changing values |
| **Max Poll Interval** | 300 seconds | Slowest polling for stable values |
| **Recovery: Consecutive Failures** | 5 | Auto-reconnect after this many failures |
| **Recovery: Data Staleness** | 10 minutes | Auto-reconnect if no data changes |

**Most users can leave these at default values.**

### Step 7: Done! 🎉

Your integration is now set up! You'll see a new device called "Neovolt [device_name]" with all your sensors and controls.

---

## ✨ Features

### 📊 Monitoring Sensors

**Grid Power**
- ⚡ Grid voltage (3-phase)
- 🔌 Grid current (3-phase)
- 📈 Grid power (import/export)
- 🔄 Grid frequency
- 📊 Power factor
- 📉 Total energy imported/exported

**Solar Production**
- ☀️ PV voltage per string (PV1, PV2, PV3)
- 🔆 PV current per string
- ⚡ PV power per string
- 📊 Total PV power (DC + AC combined)
- 📈 Total PV energy produced
- 📅 Daily PV energy (resets at midnight)

**Battery Status**
- 🔋 Battery voltage
- ⚡ Battery current
- 📊 Battery power (charge/discharge)
- 🎯 Battery state of charge (SOC %)
- 💪 Battery state of health (SOH %)
- 🌡️ Battery temperature (min/max)
- ⚡ Battery cell voltages (min/max)
- 📦 Battery capacity
- 📈 Total charge/discharge energy

**Inverter Data**
- 🌡️ Inverter temperatures (multiple zones)
- 🔌 Bus voltage
- ⚡ Active power output
- 🔌 Backup power
- 📊 Energy input/output totals

**Calculated Values**
- 🏠 House load (automatically calculated from PV + Battery + Grid)
- ☀️ Current solar production
- 📊 Excess grid export (for multi-inverter setups)

### 🎛️ Battery Control

**Dispatch Mode Select** (Single Control Point)
- 🔄 **Normal** - Automatic battery operation
- 🔋 **Force Charge** - Charge battery from grid at specified power/SOC
- 🔌 **Force Discharge** - Discharge battery at specified power/SOC
- 📊 **Dynamic Export** - Maintain target grid export power automatically
- 🚫 **No Battery Charge** - Prevent all battery charging (solar & grid)

**Dispatch Configuration (Number Entities)**
- ⚡ **Dispatch Power** - Charge/discharge power (0.5 - max kW)
- ⏱️ **Dispatch Duration** - How long to run (1-480 minutes)
- 🎯 **Dispatch Charge Target SOC** - Stop charging at % (10-100%)
- 🎯 **Dispatch Discharge Cutoff SOC** - Stop discharging at % (4-100%)
- 📊 **Dynamic Export Target** - Extra power to export beyond load (kW)

**Additional Controls**
- 🔆 **PV Switch** - Control PV input (Auto/Open/Close)
- 🛑 **Stop Force Charge/Discharge** - Quick stop button

**System Settings**
- 🌐 **Max Feed to Grid** - Limit grid export (0-100%)
- 📦 **PV Capacity** - Total PV installation capacity (Watts)
- 🔋 **Charging Cutoff SOC** - Maximum battery charge level (10-100%)
- 🔋 **Discharging Cutoff SOC (Default)** - Minimum battery discharge level (4-100%)
- ⏰ **Time Period Control** - Enable time-based charging/discharging schedules

### 🆕 What's New in Latest Version

**🔄 Improved Reliability**
- Adaptive polling automatically adjusts update frequency
- Auto-recovery from connection issues
- Better handling of temporary network hiccups
- Cached data keeps sensors available during brief disconnections

**🎯 Dynamic Export Mode**
- Automatically maintain target grid export power
- Adjusts battery charge/discharge every 10 seconds
- Perfect for maximizing solar feed-in tariff earnings

**📊 Multi-Device Support**
- Host/Follower device roles
- Configure multiple inverters independently
- Follower devices provide read-only monitoring

---

## ⚙️ Settings & Configuration

### Changing Power Limits

To update maximum charge/discharge power after installation:

1. Go to **Settings** → **Devices & Services**
2. Find **Neovolt Inverter**
3. Click the **three dots** (⋮)
4. Click **Configure**
5. Update your settings:
   - Device role (Host/Follower)
   - Power limits (Host only)
   - Polling configuration
6. Click through the configuration steps
7. Click **Submit**

The integration will reload with your new settings!

### Understanding Device Roles

**Host Device:**
- Full read/write control
- Can change settings and dispatch modes
- Use for primary control point

**Follower Device:**
- Read-only sensor access
- No control entities created
- Perfect for parallel inverter monitoring
- Lighter resource usage

---

## 🔌 Connection Troubleshooting

### Direct Ethernet Connection Issues

**Can't find inverter IP address:**
1. ✅ Check router's connected devices list
2. ✅ Look for device with MAC address starting with common inverter prefixes
3. ✅ Try scanning network with tools like "Fing" mobile app
4. ✅ Check inverter's display screen (may show IP)

**Connection refused on port 502:**
1. ✅ Verify Modbus TCP is enabled on inverter
2. ✅ Check firewall settings on network
3. ✅ Ensure port 502 isn't blocked by router
4. ✅ Try telnet test: `telnet [IP] 502`

**Intermittent connection:**
1. ✅ Assign static IP to inverter in router
2. ✅ Check Ethernet cable quality
3. ✅ Verify network switch/router is working properly
4. ✅ Review integration logs for patterns

### EW11A WiFi Adapter Issues

**Can't connect to EW11A network:**
1. ✅ Make sure EW11A is powered
2. ✅ Wait 30 seconds after power-on for WiFi to activate
3. ✅ Look for network name starting with "EW11"
4. ✅ Try factory reset if needed

**EW11A not appearing on home network:**
1. ✅ Verify WiFi credentials were entered correctly
2. ✅ Check WiFi mode is set to "STA" (Station mode)
3. ✅ Restart EW11A by unplugging and replugging
4. ✅ Check router's connected devices list
5. ✅ Ensure TCP Server mode is enabled on port 502

**For detailed EW11A setup:** See the [complete hardware setup guide](https://github.com/pvandenh/NeovoltBattery_ModbusPlugin/blob/main/custom_components/neovolt/Neovolt_Modbus%20initial%20hardware%20setup.docx)

---

## ❓ Troubleshooting

### "Cannot Connect" Error

**Problem**: Integration can't connect to inverter

**Solutions**:

**For Direct Ethernet Connection:**
1. ✅ Verify inverter is powered on
2. ✅ Check IP address is correct (look in router's device list)
3. ✅ Ping the IP address from Home Assistant Terminal: `ping [IP]`
4. ✅ Check Ethernet cable is securely connected
5. ✅ Verify Modbus TCP is enabled on inverter (should be by default)
6. ✅ Try rebooting the inverter
7. ✅ Check Home Assistant logs for detailed error messages

**For EW11A Connection:**
1. ✅ Check EW11A is powered on and connected to network
2. ✅ Verify IP address is correct
3. ✅ Ping the IP address from Home Assistant Terminal
4. ✅ Check port 502 is open (firewall)
5. ✅ Ensure EW11A is in TCP Server mode
6. ✅ Verify serial settings (9600 baud, Modbus protocol)
7. ✅ Try rebooting the EW11A converter

### Sensors Show "Unavailable"

**Problem**: Integration connected but sensors have no data

**Solutions**:
1. ✅ Check Slave ID is correct (default: 85)
2. ✅ Verify physical connection to inverter (Ethernet or RS485)
3. ✅ Check inverter is powered on and operational
4. ✅ Wait a few minutes for initial polling to complete
5. ✅ Reload integration: Settings → Devices & Services → Neovolt → ⋮ → Reload
6. ✅ Check logs: Settings → System → Logs (search for "neovolt")
7. ✅ Try increasing min poll interval if seeing connection errors

### Force Charge/Discharge Not Working

**Problem**: Dispatch mode changes but nothing happens

**Solutions**:
1. ✅ Check battery SOC is within allowed range
2. ✅ Verify inverter is in correct mode (not in maintenance, etc.)
3. ✅ Ensure grid connection is available (for charging from grid)
4. ✅ Check battery isn't in protection mode
5. ✅ Verify power setting is above minimum (0.5kW)
6. ✅ Check dispatch status sensor for error messages
7. ✅ Try "Stop Force Charge/Discharge" button first
8. ✅ Review logs for Modbus write errors

### Battery Not Reaching 100% SOC

**Problem**: Force charge stops at 99.5% or 98%

**This is FIXED in the latest version!**

**Solutions**:
1. ✅ Update to the latest integration version (includes SOC fix)
2. ✅ Verify charge target SOC is set to 100%
3. ✅ If you were using workarounds (e.g., 102% target), reset to 100%
4. ✅ Check battery isn't hitting other limits (voltage, temperature)

### Power Sliders Limited

**Problem**: Can't set higher power even with multiple inverters

**Solutions**:
1. ✅ Go to Settings → Devices & Services → Neovolt → ⋮ → Configure
2. ✅ Go through Device Role → Power Limits steps
3. ✅ Update Max Charge Power and Max Discharge Power
4. ✅ Enter total combined capacity (e.g., 15 for three 5kW units)
5. ✅ Click Submit through all steps
6. ✅ Integration will reload with new limits

### Data Age / Stale Data Warnings

**Problem**: Sensors show "data_stale" attribute as true

**What this means:**
- Integration is using cached data
- Connection may be intermittent
- Auto-recovery will attempt reconnection

**Solutions**:
1. ✅ Check network connection stability
2. ✅ Review logs for connection errors
3. ✅ Consider increasing min poll interval
4. ✅ Verify Modbus gateway isn't overloaded
5. ✅ Sensors will auto-recover when connection restored
6. ✅ Data older than 12 hours will mark entities unavailable

---

## 📝 Enable Debug Logging

If you need to troubleshoot, enable detailed logging:

1. Edit `/config/configuration.yaml`
2. Add this section:

```yaml
logger:
  default: info
  logs:
    custom_components.neovolt: debug
    pymodbus: debug
```

3. Restart Home Assistant
4. Check logs: Settings → System → Logs
5. Search for "neovolt" to see all integration activity

**What to look for in logs:**
- Connection attempts and success/failure
- Modbus register reads and writes
- Adaptive polling interval changes
- Auto-recovery triggers
- Data age tracking


---

## 📱 Getting Help

If you're stuck:

1. **Check the logs first**: Settings → System → Logs (search for "neovolt")
2. **Search existing issues**: https://github.com/pvandenh/NeovoltBattery_ModbusPlugin/issues
3. **Create a new issue** with:
   - Home Assistant version
   - Integration version (check HACS)
   - Connection type (Direct Ethernet or EW11A)
   - Device role configuration (Host/Follower)
   - Error messages from logs (enable debug logging)
   - What you've tried
   - Screenshots (if helpful)

**Home Assistant Community**: You can also ask for help on the Home Assistant forums!

---

## 🔧 Advanced Configuration

### Multiple Inverter Setup (Parallel/Master-Slave)

**Recommended Configuration:**

1. **Master/Host Inverter:**
   - Device Role: **Host**
   - Full control capabilities
   - Configure with total system capacity

2. **Slave/Follower Inverters:**
   - Device Role: **Follower**
   - Read-only monitoring
   - Lighter resource usage

**Example: Three 5kW Inverters in Parallel**

Host Device (Master):
- Max Charge Power: 15 kW
- Max Discharge Power: 15 kW
- All control entities available

Follower Devices (Slaves):
- Sensor entities only
- Monitor individual inverter performance
- No control entities

### Optimizing Polling Performance

The integration uses adaptive polling that automatically adjusts based on data changes:

**Default Behavior:**
- Fast polling (10s) for actively changing values
- Slow polling (300s) for stable values
- Auto-recovery on connection issues

**Tuning for Your Setup:**

**Slower, More Stable Networks:**
```
Min Poll Interval: 15 seconds
Max Poll Interval: 600 seconds
Consecutive Failures: 10
Staleness Threshold: 20 minutes
```

**Faster, Reliable Networks:**
```
Min Poll Interval: 10 seconds (minimum allowed)
Max Poll Interval: 120 seconds
Consecutive Failures: 3
Staleness Threshold: 5 minutes
```

---

## 🌟 Contributing

Want to contribute? Pull requests welcome!

**Areas for Contribution:**
- Bug fixes
- Feature enhancements
- Documentation improvements

---

## 📄 License

MIT License - Feel free to use, modify, and share!

---

## 👍 Credits

- Based on Bytewatt Modbus RTU Protocol V1.12
- Integration developed for the Home Assistant community
- Special thanks to Claude.ai for development assistance
- Thanks to all contributors and testers!

---

## 📋 Version History

### Latest Release
- ✅ **Fixed critical SOC conversion bug** - battery now correctly reaches 100%
- 🔄 Adaptive polling for improved reliability
- 🎯 Dynamic Export mode for grid export control
- 📊 Multi-device support with Host/Follower roles
- 🛡️ Auto-recovery from connection issues
- 📈 Better handling of unavailable sensors
- 🔧 Configurable polling intervals

### Previous Versions
- See GitHub releases for detailed changelog

---

**You're all set! ☀️🔋**

---

*For technical documentation, Modbus protocol details, and advanced features, see the repository wiki and source code documentation.*
