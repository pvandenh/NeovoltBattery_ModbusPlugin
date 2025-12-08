# Neovolt Inverter Integration for Home Assistant

A Home Assistant custom integration for Neovolt/Bytewatt inverters and battery systems using Modbus TCP protocol.

<img width="225" height="80" alt="image" src="https://github.com/user-attachments/assets/fd21d47f-ff23-44cb-bd60-02c9f13d0f06" />

## 🎯 What Does This Do?

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
| **Max Charge Power** | Maximum charging power in kW | `5.0` (single inverter)<br>`15.0` (three inverters) |
| **Max Discharge Power** | Maximum discharging power in kW | `5.0` (single inverter)<br>`15.0` (three inverters) |

**Finding Your IP Address:**

- **Direct Ethernet**: Check your router's device list for "Neovolt" or "Bytewatt"
- **EW11A**: Check router for "EW11A" or check the EW11A's display screen
- **Alternative**: Use a network scanner app on your phone

**Multiple Inverters?**
If you have a parallel/master-slave setup, enter the **total combined capacity**. For example, three 5kW inverters = 15kW total.

### Step 5: Done! 🎉

Your integration is now set up! You'll see a new device called "Neovolt Inverter" with all your sensors and controls.

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

**Intermittent connection:**
1. ✅ Assign static IP to inverter in router
2. ✅ Check Ethernet cable quality
3. ✅ Verify network switch/router is working properly

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

**For detailed EW11A setup:** See the [complete hardware setup guide](https://github.com/pvandenh/NeovoltBattery_ModbusPlugin/blob/main/custom_components/neovolt/Neovolt_Modbus%20initial%20hardware%20setup.docx)

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
- 📊 Total PV power
- 📈 Total PV energy produced

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
- 🏠 House load (automatically calculated)
- ☀️ Current solar production

### 🎛️ Controls

**Battery Control Switches**
- 🔋 **Force Charging** - Charge battery from grid
- 🔌 **Force Discharging** - Discharge battery to grid/house
- 🚫 **Prevent Solar Charging** - Stop battery charging from solar

**Power Settings (Sliders)**
- ⚡ **Force Charging Power** - How fast to charge (0.5 - configured max kW)
- ⏱️ **Force Charging Duration** - How long to charge (1-480 minutes)
- 🎯 **Charging SOC Target** - Stop charging at this % (10-100%)
- ⚡ **Force Discharging Power** - How fast to discharge (0.5 - configured max kW)
- ⏱️ **Force Discharging Duration** - How long to discharge (1-480 minutes)
- 🎯 **Discharging SOC Cutoff** - Stop discharging at this % (4-50%)
- ⏱️ **Prevent Solar Charging Duration** - How long to block solar charging (1-1440 minutes)

**System Settings**
- 🌐 **Max Feed to Grid** - Limit grid export (0-100%)
- 🔋 **Charging Cutoff SOC** - Maximum battery charge level (10-100%)
- 🔋 **Discharging Cutoff SOC** - Minimum battery discharge level (4-100%)
- ⏰ **Time Period Control** - Enable time-based charging/discharging schedules

**Quick Actions (Buttons)**
- 🛑 **Stop Force Charge/Discharge** - Quickly stop all force charging / discharging commands

---

## ⚙️ Settings & Configuration

### Changing Power Limits

To update maximum charge/discharge power after installation:

1. Go to **Settings** → **Devices & Services**
2. Find **Neovolt Inverter**
3. Click the **three dots** (⋮)
4. Click **Configure**
5. Update your power limits
6. Click **Submit**

The integration will reload with your new settings!

---

## 🎨 Dashboard Card Example

Create a simple dashboard card to monitor your system:

```yaml
type: entities
title: Neovolt Solar System
entities:
  - entity: sensor.neovolt_inverter_battery_soc
    name: Battery Level
    icon: mdi:battery
  - entity: sensor.neovolt_inverter_battery_power
    name: Battery Power
  - entity: sensor.neovolt_inverter_current_pv_production
    name: Solar Production
  - entity: sensor.neovolt_inverter_grid_total_active_power
    name: Grid Power
  - entity: sensor.neovolt_inverter_total_house_load
    name: House Load
  - type: divider
  - entity: switch.neovolt_inverter_force_charging
    name: Force Charge
  - entity: switch.neovolt_inverter_force_discharging
    name: Force Discharge
  - entity: number.neovolt_inverter_force_charging_power
    name: Charge Power
  - entity: number.neovolt_inverter_force_discharging_power
    name: Discharge Power
```

---

## ❓ Troubleshooting

### "Cannot Connect" Error

**Problem**: Integration can't connect to inverter

**Solutions**:

**For Direct Ethernet Connection:**
1. ✅ Verify inverter is powered on
2. ✅ Check IP address is correct (look in router's device list)
3. ✅ Ping the IP address from Home Assistant Terminal
4. ✅ Check Ethernet cable is securely connected
5. ✅ Verify Modbus TCP is enabled on inverter (should be by default)
6. ✅ Try rebooting the inverter

**For EW11A Connection:**
1. ✅ Check EW11A is powered on and connected to network
2. ✅ Verify IP address is correct
3. ✅ Ping the IP address from Home Assistant Terminal
4. ✅ Check port 502 is open (firewall)
5. ✅ Ensure EW11A is in TCP Server mode
6. ✅ Try rebooting the EW11A converter

### Sensors Show "Unavailable"

**Problem**: Integration connected but sensors have no data

**Solutions**:
1. ✅ Check Slave ID is correct (default: 85)
2. ✅ Verify physical connection to inverter (Ethernet or RS485)
3. ✅ Check inverter is powered on and operational
4. ✅ Reload integration: Settings → Devices & Services → Neovolt → ⋮ → Reload
5. ✅ Check logs: Settings → System → Logs (search for "neovolt")

### Force Charge/Discharge Not Working

**Problem**: Switch turns on but nothing happens

**Solutions**:
1. ✅ Check battery SOC is within allowed range
2. ✅ Verify inverter is in correct mode (not in maintenance, etc.)
3. ✅ Ensure grid connection is available (for charging)
4. ✅ Check battery isn't in protection mode
5. ✅ Try pressing the "Dispatch Reset" button first

### Power Sliders Limited to 5kW

**Problem**: Can't set higher power even with multiple inverters

**Solutions**:
1. ✅ Go to Settings → Devices & Services → Neovolt → ⋮ → Configure
2. ✅ Update Max Charge Power and Max Discharge Power
3. ✅ Enter total combined capacity (e.g., 15 for three 5kW units)
4. ✅ Click Submit
5. ✅ Integration will reload with new limits

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

---

## 📱 Getting Help

If you're stuck:

1. **Check the logs first**: Settings → System → Logs
2. **Search existing issues**: https://github.com/pvandenh/NeovoltBattery_ModbusPlugin/issues
3. **Create a new issue** with:
   - Home Assistant version
   - Integration version
   - Connection type (Direct Ethernet or EW11A)
   - Error messages from logs
   - What you've tried
   - Screenshots (if helpful)

**Home Assistant Community**: You can also ask for help on the Home Assistant forums!

---

## 🌟 Features Roadmap

Want to contribute? Pull requests welcome!

---

## 📄 License

MIT License - Feel free to use, modify, and share!

---

## 👍 Credits

- Based on Bytewatt Modbus RTU Protocol V1.12
- Integration developed for the Home Assistant community, assisted by Claude.ai
- Thanks to all contributors and testers!

---

## ⚡ Quick Start Checklist

- [ ] HACS installed
- [ ] Custom repository added to HACS
- [ ] Integration installed via HACS
- [ ] Home Assistant restarted
- [ ] **Connection hardware setup** (Direct Ethernet OR EW11A)
- [ ] IP address of inverter/EW11A noted
- [ ] Integration added via Settings → Devices & Services
- [ ] Connection details entered correctly
- [ ] Max power configured (if multiple inverters)
- [ ] Integration showing data
- [ ] Added to Energy Dashboard
- [ ] Created first automation
- [ ] Created dashboard card

**You're all set! ☀️🔋**

---

*For technical documentation and advanced features, see the full documentation on GitHub.*
