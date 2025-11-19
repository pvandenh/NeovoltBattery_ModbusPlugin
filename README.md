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
- ✅ **EW11A Modbus converter** (or compatible) - this connects your inverter to your network
- ✅ Home Assistant installed and running

### Software
- ✅ Home Assistant 2023.1 or newer
- ✅ HACS (Home Assistant Community Store) installed

**Don't have HACS?** Install it first: https://hacs.xyz/docs/setup/download

---

## 📦 Installation

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
| **Host (IP Address)** | IP address of your EW11A Modbus converter | `192.168.1.100` |
| **Port** | Leave as default | `502` |
| **Slave ID** | Leave as default | `85` |
| **Max Charge Power** | Maximum charging power in kW | `5.0` (single inverter)<br>`15.0` (three inverters) |
| **Max Discharge Power** | Maximum discharging power in kW | `5.0` (single inverter)<br>`15.0` (three inverters) |

**Finding Your IP Address:**
- Check your router's device list for "EW11A" or similar
- Check the EW11A display screen
- Use a network scanner app

**Multiple Inverters?**
If you have a parallel/master-slave setup, enter the **total combined capacity**. For example, three 5kW inverters = 15kW total.

### Step 5: Done! 🎉

Your integration is now set up! You'll see a new device called "Neovolt Inverter" with all your sensors and controls.

---

## 🔌 Hardware Setup (EW11A Modbus Converter)

If you haven't connected your EW11A converter yet:

1. **Connect to Inverter**
   - Plug the EW11A into the inverter's RS485 port

2. **Connect to Network**
   - Connect the EW11A to your router

3. **Configure EW11A**
   - Connect to the EW11A via its IP address in a web browser
   - Set it to **TCP Server** mode
   - Set port to **502**
   - Set baud rate to **9600** (or as per inverter manual)
   - Save and reboot

4. **Test Connection**
   - Make sure the EW11A has a fixed IP address (set in your router)
   - Ping the IP address from Home Assistant Terminal:
     ```
     ping 192.168.1.100
     ```

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
- ⏱️ **Force Charging Duration** - How long to charge (5-480 minutes)
- 🎯 **Charging SOC Target** - Stop charging at this % (10-100%)
- ⚡ **Force Discharging Power** - How fast to discharge (0.5 - configured max kW)
- ⏱️ **Force Discharging Duration** - How long to discharge (5-480 minutes)
- 🎯 **Discharging SOC Cutoff** - Stop discharging at this % (4-50%)
- ⏱️ **Prevent Solar Charging Duration** - How long to block solar charging (15-1440 minutes)

**System Settings**
- 🌐 **Max Feed to Grid** - Limit grid export (0-100%)
- 🔋 **Charging Cutoff SOC** - Maximum battery charge level (10-100%)
- 🔋 **Discharging Cutoff SOC** - Minimum battery discharge level (4-100%)
- ⏰ **Time Period Control** - Enable time-based charging/discharging schedules

**Quick Actions (Buttons)**
- 🔄 **Dispatch Reset** - Stop all force charge/discharge
- 🛑 **Stop Charging** - Quickly stop force charging
- 🛑 **Stop Discharging** - Quickly stop force discharging

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
2. ✅ Verify RS485 connection to inverter
3. ✅ Check inverter is powered on
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

## 🔍 Enable Debug Logging

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

## 👏 Credits

- Based on Bytewatt Modbus RTU Protocol V1.12
- Integration developed for the Home Assistant community, assisted by Claude.ai
- Thanks to all contributors and testers!

---

## ⚡ Quick Start Checklist

- [ ] HACS installed
- [ ] Custom repository added to HACS
- [ ] Integration installed via HACS
- [ ] Home Assistant restarted
- [ ] EW11A converter connected and configured
- [ ] IP address of EW11A noted
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
