# บทวิเคราะห์แผนงานโครงการ MTAI (Forex AI Trading System)

ภาพรวมของแผนงานโครงการ **MTAI** คือการพอร์ต (Port) ระบบ AI Trading จากเดิมที่ทำงานบนตลาด Crypto (Binance/CCXT) ไปยังตลาด Forex (MetaTrader 5 + Exness) โดยยังคงรักษาลอจิกแกนหลัก (เช่น Genetic Algorithm, Mean Reversion, Grid Scalping) ไว้ แต่ปรับเปลี่ยน Data Feed และ Execution Layer

จากการตรวจสอบแผนงานในไฟล์ `PLAN.md` และรายละเอียดของแต่ละ Phase ในโฟลเดอร์ `phases/` ทางเราได้ทำการวิเคราะห์ความสมบูรณ์และพบ **ช่องว่างทางสถาปัตยกรรม (Architectural Gaps)** และ **ข้อผิดพลาดทางตรรกะ (Logical Bugs)** ที่สำคัญในโค้ดตัวอย่าง ดังรายละเอียดด้านล่างนี้:

---

## 1. ข้อผิดพลาดทางตรรกะที่วิกฤต (Critical Logical Bugs)

### 🔴 Bug 1.1: คำนวณ Lot Size ผิดพลาดสำหรับคู่เงินที่ไม่ได้ Quote ด้วย USD (`pip_calc.py`)
ในฟังก์ชัน `calculate_lot_size` มีการคำนวณมูลค่า Pip ด้วยสูตร:
```python
pip_value_per_lot = pip_size * contract_size  # assumption: USD per pip per lot
```
* **ปัญหา:** สูตรนี้ใช้ได้เฉพาะกับคู่เงินที่ Quote ด้วย USD เท่านั้น (เช่น EURUSD, GBPUSD, AUDUSD, XAUUSD) ซึ่งมูลค่า Pip ต่อ 1 Lot จะเท่ากับ $10 USD (หรือ $100 สำหรับ Gold) เสมอ
* **ข้อผิดพลาดสำหรับคู่เงินอื่น:**
  1. **USD-Base (เช่น USDJPY, USDCAD, USDCHF):** มูลค่า Pip จะเป็นสกุลเงิน Quote (เช่น JPY, CAD) ซึ่งต้องนำมาหารด้วยราคาปัจจุบัน (Current Price) เพื่อแปลงกลับเป็น USD (สกุลเงินของบัญชีเทรด) เช่น 1 Lot ของ USDJPY มีมูลค่า 1,000 JPY/pip หากราคาอยู่ที่ 150.00 จะคิดเป็น `1000 / 150 = 6.67` USD/pip การไม่หารจะทำให้คำนวณ Lot Size เล็กเกินไปอย่างมาก
  2. **Cross Pairs (เช่น EURGBP, EURJPY):** จะต้องใช้ราคาของคู่เงินเชื่อมโยง (เช่น GBPUSD หรือ USDJPY) มาแปลงค่า Pip ให้เป็น USD
* **ผลกระทบ:** ระบบจะคำนวณ Risk ผิดพลาด (อาจเทรด Lot เล็กเกินไปจนไม่มีกำไร หรือใหญ่เกินไปจนโอเวอร์เทรด)

### 🔴 Bug 1.2: การตรวจสอบ Trading Session ขัดแย้งกันเอง (`signals.py`)
ในฟังก์ชัน `get_current_session()` และ `is_good_session()` มีการจัดการช่วงทับซ้อน (Overlap) ดังนี้:
```python
def get_current_session() -> str:
    hour = datetime.now(timezone.utc).hour
    if 13 <= hour < 16:
        return "OVERLAP"
    ...
```
* **ปัญหา:** หากเวลาเป็น 14:00 UTC ฟังก์ชันจะส่งกลับค่า `"OVERLAP"` ทันที
* **ข้อขัดแย้ง:** ใน `SESSION_SYMBOL_AFFINITY` คู่เงินอย่าง `USDCAD` มีค่าเป็น `["NY"]` แต่เนื่องจาก `get_current_session()` คืนค่าเป็น `"OVERLAP"` การตรวจสอบใน `is_good_session()` จะได้ผลลัพธ์เป็น `False` (เนื่องจาก `"OVERLAP"` ไม่อยู่ใน `["NY"]`)
* **ผลกระทบ:** คู่เงินที่เป็น NY-only เช่น USDCAD จะถูกบล็อกไม่ให้เทรดในช่วงเวลาคาบเกี่ยว (13:00 - 16:00 UTC) ซึ่งเป็นช่วงที่มีสภาพคล่องและโวลุ่มสูงที่สุดของฝั่งอเมริกา

### 🔴 Bug 1.3: ตัวนับ Tick ทำงานแบบ Global ไม่แยก Symbol (`agent_manager.py`)
ใน `ForexAgentManager.on_tick`:
```python
self._tick_count += 1
if self._tick_count % 10 == 0:
    await self._process_agents(symbol, price)
```
* **ปัญหา:** `self._tick_count` จะเพิ่มขึ้นทุกครั้งที่มี Tick เข้ามาจากสกุลเงินใดๆ ใน 8 สกุลเงิน
* **ผลกระทบ:** ความถี่ในการตัดสินใจของแต่ละ Agent จะไม่สม่ำเสมอและขึ้นอยู่กับกิจกรรมของคู่เงินอื่น (เช่น หาก EURUSD วิ่งแรงมาก มันจะไปกระตุ้นให้ USDJPY ประมวลผลสัญญาณสัญญาณ ทั้งๆ ที่ USDJPY เพิ่งขยับไปเพียง Tick เดียว)

---

## 2. ช่องว่างทางสถาปัตยกรรม (Architectural Gaps)

### ⚠️ Gap 2.1: ไม่มีระบบตรวจสอบและอัปเดตสถานะการปิดออเดอร์ (Order Sync Loop)
ใน `ForexAgentManager` มีเพียงฟังก์ชันในการเปิดออเดอร์ (`_live_execute` / `_paper_execute`) แต่ **ไม่มีส่วนที่คอยตรวจสอบว่าออเดอร์นั้นถูกปิดไปแล้วหรือยัง**
* **สำหรับ Live Trading:** เมื่อราคาชน SL หรือ TP บน Broker (Exness) ทาง MT5 จะปิดออเดอร์อัตโนมัติ แต่ในฝั่ง Python ตัวแปร `agent._open_ticket` จะยังคงค้างอยู่ตลอดไป ทำให้ Agent นั้นถูกมองว่า `is_in_trade = True` และจะไม่เทรดอีกเลย รวมถึงไม่สามารถบันทึกผลการเทรด (Win Rate, PnL) เข้าสู่ระบบ Evolution ได้
* **สำหรับ Paper Trading:** ไม่มีลอจิกคอยเช็คราคา Tick ปัจจุบันกับจุด SL/TP ของ Agent ส่งผลให้ออเดอร์จำลองค้างเติ่งถาวร

### ⚠️ Gap 2.2: การรับมือกับประเภทการส่งคำสั่ง (Filling Mode) ของ Broker
ใน `mt5_api_server.py` มีการฮาร์ดโค้ด `"type_filling": mt5.ORDER_FILLING_IOC`
* **ปัญหา:** บัญชีต่างประเภทของ Exness (เช่น Raw Spread vs Standard) หรือต่าง Broker มีข้อกำหนด Filling Mode ที่ต่างกัน หากส่งคำสั่งด้วย IOC ไปยังเซิร์ฟเวอร์ที่รองรับเฉพาะ FOK (Fill or Kill) หรือ RETURN ออเดอร์จะถูกปฏิเสธทันทีด้วยรหัส Retcode 10030 (Unsupported filling mode)

### ⚠️ Gap 2.3: ปัญหาเรื่อง Timezone และ DST สำหรับ Macro Events
ใน `forex_macro.py` มีการกำหนดเวลาการประกาศข่าว NFP แบบตายตัวที่ชั่วโมง 12:30 UTC
* **ปัญหา:** สหรัฐอเมริกามีการปรับเวลาตามฤดูกาล (DST) ทำให้เวลาในการประกาศข่าวเลื่อนระหว่าง 12:30 UTC (ช่วง Daylight Saving) และ 13:30 UTC (ช่วงเวลามาตรฐาน) การเช็คเวลาแบบ Hardcoded จะใช้ไม่ได้ผลครึ่งปี

---

## 3. การประเมินและวิเคราะห์ตามเฟส (Phase Evaluation)

| Phase | วัตถุประสงค์ | ความพร้อมและจุดที่ต้องปรับปรุง |
| :--- | :--- | :--- |
| **Phase 1: MT5 Bridge** | เชื่อมต่อข้อมูลราคาและคำสั่งเทรดกับ MT5 API | **ดีมาก:** สถาปัตยกรรม Option A (FastAPI บน Windows) ช่วยตัดปัญหาเรื่องความไม่เสถียรของ Wine บน Linux ได้เด็ดขาด<br>**จุดแก้ไข:** ต้องแก้บั๊กคำนวณ Pip Value ใน `pip_calc.py` และทำระบบ Dynamic Filling Mode |
| **Phase 2: Signal Engine** | พอร์ตอัลกอริทึมจาก Crypto และปรับตัวแปร | **ดี:** Technical Indicators ส่วนใหญ่ใช้ของเดิมได้ทันทีเนื่องจากเป็น Pure Math<br>**จุดแก้ไข:** แก้ตรรกะตรวจสอบ Session ใน `signals.py` และดึงข่าวจาก Economic Calendar API จริงในระยะยาว |
| **Phase 3: Risk Engine** | ตรวจสอบ Risk และคำนวณ Lot Size | **ดี:** มีกฎเหล็กชัดเจน (1% Risk, R:R >= 1:2, Daily Drawdown)<br>**จุดแก้ไข:** เพิ่มฟังก์ชัน Margin Check เพื่อป้องกันไม่ให้ส่งออเดอร์ Lot ใหญ่เกินไปจนเกิด Margin Call ก่อนชน SL |
| **Phase 4: Agent System** | รัน 25 Agents และระบบ Evolution | **ดี:** การลดลงเหลือ 25 agents และใช้แนวคิด Symbol Specialization มีความเหมาะสมมากกับ Forex<br>**จุดแก้ไข:** เพิ่มลอจิกรวบรวมผลการเทรดที่ปิดไปแล้วเพื่อป้อนให้ระบบ Genetic Algorithm ทำงานได้จริง |
| **Phase 5: Dashboard** | แสดงผลสถานะระบบเทรด | **ดี:** ใช้แนวทางเขียนสถานะลง `live_state.json` แล้วให้ Static HTML มา Poll ช่วยลดภาระของ Trading Loop<br>**จุดแก้ไข:** ควรปรับปรุง UI ของ Dashboard ให้ดูโมเดิร์นและตอบสนองได้รวดเร็วขึ้น |

---

## 4. ข้อเสนอแนะเชิงรหัส (Suggested Code Refactoring)

### แก้ไข Bug 1.1 (Pip Value Calculator)
ปรับปรุง `pip_calc.py` ให้รองรับคู่เงินหลากหลายประเภท:
```python
def calculate_lot_size(
    account_balance: float,
    risk_pct: float,
    sl_price_distance: float,
    symbol: str,
    contract_size: float = 100_000,
    current_price: float = 1.0,
    base_to_usd_rate: float = 1.0,  # ราคาสกุลเงิน base เทียบกับ USD (ถ้าจำเป็น)
) -> float:
    risk_amount = account_balance * risk_pct
    pip_size = get_pip_size(symbol)
    sl_pips = sl_price_distance / pip_size
    
    # คำนวณมูลค่า Pip ในสกุลเงิน Quote
    pip_value_quote = pip_size * contract_size
    
    # แปลงสกุลเงิน Quote กลับมาเป็น USD (สมมติบัญชีเป็น USD)
    if symbol.endswith("USD"):  # EURUSD, XAUUSD
        pip_value_usd = pip_value_quote
    elif symbol.startswith("USD"):  # USDJPY, USDCAD
        pip_value_usd = pip_value_quote / current_price
    else:  # Cross pairs e.g. EURGBP
        pip_value_usd = pip_value_quote * base_to_usd_rate
        
    if sl_pips == 0 or pip_value_usd == 0:
        return 0.01
        
    lot_size = risk_amount / (sl_pips * pip_value_usd)
    return max(0.01, min(10.0, round(lot_size, 2)))
```

### แก้ไข Gap 2.1 (เพิ่ม Loop ตรวจสอบออเดอร์ที่ปิดใน Agent Manager)
ตัวอย่างการเพิ่มการตรวจสอบใน `ForexAgentManager`:
```python
async def sync_positions(self):
    """รันทุกๆ 60 วินาที เพื่ออัปเดตสถานะออเดอร์ที่ปิดแล้ว"""
    try:
        active_positions = await self.mt5.get_positions()
        active_tickets = {p["ticket"] for p in active_positions}
        
        for agent in self.agents:
            if agent.is_in_trade and not agent.paper_mode:
                if agent._open_ticket not in active_tickets:
                    # ออเดอร์ปิดแล้ว -> ดึงข้อมูล PnL จาก History ของ MT5
                    pnl_info = await self.mt5.get_deal_history(agent._open_ticket)
                    agent.record_trade_result(pnl_info["pnl"], pnl_info["pnl_pct"])
                    self.risk_guardian.on_position_closed(pnl_info["pnl"])
                    agent._open_ticket = None
    except Exception as e:
        logger.error(f"Sync positions failed: {e}")
```
