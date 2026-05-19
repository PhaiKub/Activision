# Requirements Document

## Introduction

พอร์ตฟีเจอร์ของ Charge-Grinder v3.4.0 (อ้างอิง release notes ที่ผู้ใช้ให้และต้นฉบับใน `c:\Users\Colors\Documents\GitHub\Charge-Grinder`) เข้ามาในโปรเจกต์ Activision โดยที่ Activision เป็น fork ที่เปลี่ยน input transport จาก `bridge.dll` (CDECL DLL บน Windows) ไปใช้ ESP32 HID bridge สามรูปแบบ ได้แก่ ESP32 BLE HID (WiFi TCP / Bluetooth SPP) และ ESP32-S3 USB HID (USB CDC). ฟีเจอร์ที่จะพอร์ตประกอบด้วยสี่ส่วน:

1. **Human-like mouse movement** จากโมเดล arc-length θ(s) ที่เทรนจาก trajectory จริงของผู้พัฒนา (`source/utils/movement/`).
2. **Auto pointer-speed learning** ที่เรียนรู้ scale ของ pointer แล้วปรับ relative-move output ให้ตรงกับการเคลื่อนของ cursor จริง (`source/utils/movement/pointer_gain.py`).
3. **12 packs ใหม่** ที่เพิ่มเข้ามาใน `source/utils/paths.py` ของ Charge-Grinder (10 ใน 12 เป็น extreme).
4. **Key-press fallback** ที่นับจำนวน fail แล้วสลับไปใช้ mouse click เมื่อ key press ไม่ทำงาน (`p.KEY_ERRORS` + `input_with_fallback`).

การพอร์ตต้อง:
- **เคารพสถาปัตยกรรมเดิมของ Activision** ไม่ทับโค้ด Bridge.dll ที่ Activision ลบไปแล้ว ต้องไหลผ่าน ESP32 HID transport ทั้งหมด.
- **รักษาความเข้ากันได้ย้อนหลัง** กับ config, packs, และ firmware variant ทั้งสามแบบของ Activision.
- **ปรับโมเดลการเคลื่อนเมาส์ให้ทำงานบน HID transport** ที่จำกัด `dx/dy` ที่ ±127 ต่อ packet และมี latency 5–50ms ต่อ command.

## Glossary

- **Activision**: โปรเจกต์ปลายทางที่ `c:\Users\Colors\Documents\GitHub\Activision`.
- **Charge-Grinder (CG)**: โปรเจกต์ต้นทางที่ `c:\Users\Colors\Documents\GitHub\Charge-Grinder` ที่ release tag v3.4.0.
- **HID Bridge**: คลาส abstraction ที่ Activision ใช้ส่ง mouse/keyboard event ผ่าน ESP32 hardware ปัจจุบันมี `ESP32Bridge` (BLE/SPP) และ `ESP32S3Bridge` (USB CDC) ที่ `source/utils/bridge/`.
- **Bridge_Mode**: ค่าใน `p.BRIDGE_MODE` ที่เลือก `"esp32"` หรือ `"esp32s3"` ระหว่างรันไทม์.
- **Movement_Model**: โมเดล GMM-based บน arc-length θ(s) ที่อยู่ในไฟล์ `source/utils/movement/model.npz` ของ Charge-Grinder.
- **Trajectory_Builder**: โมดูล `source.utils.movement.builder` ที่สร้างเส้นทาง waypoint จากจุดเริ่ม → จุดปลาย.
- **Pointer_Gain_Tracker**: state object ใน `source.utils.movement.pointer_gain` ที่ track scale ของ pointer.
- **Inertia_Tracker**: state object ใน `source.utils.movement.inertia` ที่ track velocity ที่ inherit จาก move ก่อนหน้า.
- **Trajectory_Executor**: ฟังก์ชัน `execute_trajectory` ที่อ่าน path + times แล้ว emit relative-move ผ่าน HID Bridge ตามตารางเวลา.
- **OS_Backend**: โมดูล `source/utils/os_windows_backend.py` ของ Activision ที่ wrap HID Bridge เป็น API ระดับสูง (`moveTo`, `click`, `press`, `dragTo`, `scroll`).
- **Pack**: รายการ "TheForgotten", "Line1Madness" ฯลฯ ที่ Activision ใช้เลือก floor card ใน Mirror Dungeon, นิยามใน `source/utils/paths.py` ที่ dict `PACKS`.
- **PACKS_Map**: dict `PACKS` ใน `paths.py` ที่ map `pack_name → ((normal_floors_tuple), (hard_floors_tuple))`.
- **Key_Error_Counter**: ตัวนับ fail ของ key press ระดับ global ใน `p.KEY_ERRORS`.
- **Input_With_Fallback**: ฟังก์ชัน utility `input_with_fallback(key, mouse_action, ver_func)` ที่ลอง keyboard ก่อน fallback ไป mouse.
- **Verifier_Func**: callable ที่คืน `True` ถ้า action ที่กดสำเร็จ (เช่น เปลี่ยนหน้า, เกิด button ที่คาด).
- **HID_Sample_Rate**: rate ที่ใช้ส่ง relative-move event ทาง HID Bridge หน่วย Hz.
- **Pointer_Scale**: float ใน `_POINTER_STATE["scale"]` ที่คูณกับ raw model output เพื่อให้ pixel เคลื่อนตรงกับ target.

## Requirements

### Requirement 1: Human-like Mouse Movement Model

**User Story:** As a Mirror Dungeon grinder, I want the bot to move the mouse along human-like curves driven by the trained model, so that the cursor trajectory mimics real human play and is harder to flag by heuristic anti-cheat.

#### Acceptance Criteria

1. THE Activision SHALL include the file `source/utils/movement/model.npz` copied unchanged from `c:\Users\Colors\Documents\GitHub\Charge-Grinder\source\utils\movement\model.npz`.
2. THE Activision SHALL include the modules `source/utils/movement/__init__.py`, `source/utils/movement/generator.py`, `source/utils/movement/builder.py`, `source/utils/movement/inertia.py`, and `source/utils/movement/pointer_gain.py` ported from Charge-Grinder v3.4.0.
3. WHEN `Trajectory_Builder.build_trajectory(start, end, ...)` is called with a non-zero distance, THE Trajectory_Builder SHALL return a dict containing `points` (Nx2 numpy array of int-rounded screen positions) and `times` (length-N monotonically non-decreasing float array starting at 0.0).
4. WHEN `Trajectory_Builder.build_trajectory(start, end, ...)` is called and `start` equals `end`, THE Trajectory_Builder SHALL return a trajectory whose first and last `points` rows both equal `start`.
5. THE returned trajectory points SHALL satisfy `points[0] == round(start)` and `points[-1] == round(biased_end)` where `biased_end` is the endpoint after applying target-size endpoint bias.
6. WHEN the same `(start, end, duration_override)` triple is fed twice with no fixed seed, THE Trajectory_Builder SHALL produce different trajectories (the model is stochastic by design).
7. WHILE the workspace lacks `model.npz`, THE Trajectory_Builder SHALL raise an exception with a message that mentions the missing model file path.
8. THE Trajectory_Builder SHALL NOT call any function from `source.utils.os_windows_backend` (the model code MUST remain transport-agnostic).

### Requirement 2: HID-Adapted Trajectory Execution

**User Story:** As a developer integrating the new movement, I want trajectory output to be emitted through the existing ESP32 HID Bridge without bypassing it, so that all three firmware variants continue to work.

#### Acceptance Criteria

1. WHEN `OS_Backend.moveTo(x, y, ...)` is called and the target differs from the current cursor position by more than `tsize` pixels, THE OS_Backend SHALL build a trajectory via `Trajectory_Builder.build_trajectory` and emit it as a series of `mouse_move_relative(dx, dy)` calls on the active HID Bridge.
2. THE OS_Backend SHALL NOT use `ctypes.windll.user32.SetCursorPos` to warp the cursor as part of normal movement (warping bypasses the model and the HID transport).
3. WHEN the trajectory contains a step whose `(dx, dy)` exceeds the HID per-packet limit of ±127, THE OS_Backend SHALL split that step into multiple `mouse_move_relative` calls each within ±127 (the existing `ESP32Bridge.mouse_move_relative` and `ESP32S3Bridge.mouse_move_relative` loops already do this).
3a. IF a single requested step exceeds 10000 pixels in either axis, THEN THE OS_Backend SHALL cap that step to ±10000 pixels and log a warning, to prevent runaway packet generation from a corrupt trajectory.
4. WHEN `Trajectory_Executor` schedules a step whose target time is later than the current monotonic clock, THE Trajectory_Executor SHALL sleep until the target time before emitting the step.
5. THE Trajectory_Executor SHALL use `time.perf_counter()` (not `time.time()`) for scheduling to avoid wall-clock drift.
6. WHEN consecutive trajectory points round to the same integer pixel, THE Trajectory_Executor SHALL skip emitting a zero-magnitude `mouse_move_relative` call.
7. WHEN `OS_Backend.moveTo` finishes a trajectory and the actual cursor (read via `GetCursorPos`) is more than 15 pixels away from the requested endpoint AND not yet within `tsize`, THE OS_Backend SHALL invoke pointer-scale update logic and rebuild a corrective trajectory from the current actual position.
7a. WHEN `OS_Backend.moveTo` finishes a trajectory and the actual cursor is exactly on the requested endpoint (zero distance), THE OS_Backend SHALL skip the corrective rebuild path and exit the move loop immediately.
8. WHEN `OS_Backend.moveTo` finishes and the cursor is within `tsize` of the target, THE OS_Backend SHALL call `Inertia_Tracker.update_inertia(raw_path, times)` so that the next move can inherit residual velocity.
9. WHEN any HID Bridge call inside the trajectory loop raises `BridgeError` (or `ESP32BridgeError` / `ESP32S3BridgeError`), THE OS_Backend SHALL propagate the exception to the caller without leaving any mouse button in a pressed state.

### Requirement 3: Auto Pointer-Speed Learning

**User Story:** As a user on a system with unknown pointer-speed settings, I want the macro to learn its real pointer scale and adjust output, so that movement lands accurately without me having to disable Windows pointer acceleration manually.

#### Acceptance Criteria

1. THE Pointer_Gain_Tracker SHALL maintain a single global scale value `_POINTER_STATE["scale"]` initialized to `1.0`.
2. WHEN `Pointer_Gain_Tracker.update_pointer_scale(accumulated_raw, start_pos, current_pos)` is called and the squared norm of `accumulated_raw` exceeds `225.0`, THE Pointer_Gain_Tracker SHALL compute `observed_scale = dot(actual_delta, raw_delta) / dot(raw_delta, raw_delta)` and EMA-blend it into `_POINTER_STATE["scale"]` with `alpha = _POINTER_STATE["alpha"]`.
3. IF the cosine similarity between `actual_delta` and `raw_delta` is below `0.85`, THEN THE Pointer_Gain_Tracker SHALL leave `_POINTER_STATE["scale"]` unchanged (the move was likely interrupted).
4. IF the absolute difference between `observed_scale` and the current scale is at most `0.03`, THEN THE Pointer_Gain_Tracker SHALL leave `_POINTER_STATE["scale"]` unchanged (avoid jitter).
5. WHEN `Trajectory_Executor.execute_trajectory(dev, raw_path, times, emit_func)` is called, THE Trajectory_Executor SHALL divide each desired raw step by `_POINTER_STATE["scale"]` before rounding to an integer `(dx, dy)`.
5a. IF `_POINTER_STATE["scale"]` becomes zero, THEN THE Trajectory_Executor SHALL allow the resulting `ZeroDivisionError` to propagate (fail-fast: a zero scale indicates a learning bug and SHALL NOT be silently substituted).
6. THE Activision SHALL NOT attempt to call any Windows pointer-acceleration registry API or `SystemParametersInfo` from Python (the ESP32 HID bridge has no equivalent of Charge-Grinder's `cg_mouse_settings_apply`; learning replaces that path on this fork).
7. WHEN the user closes the macro and reopens it later, THE Pointer_Gain_Tracker SHALL reset `_POINTER_STATE["scale"]` back to `1.0` (per-run learning, no on-disk persistence in this version).

### Requirement 4: Inherited Velocity Between Moves

**User Story:** As a player watching the bot move, I want consecutive close-spaced moves to feel like one continuous gesture instead of dead stops, so that movement looks more natural.

#### Acceptance Criteria

1. THE Inertia_Tracker SHALL store the last-observed velocity vector `_INERTIA_STATE["velocity"]` (units: pixels per second) and the timestamp at which it was recorded.
2. WHEN `Inertia_Tracker.update_inertia(raw_path, times)` is called with fewer than 4 sample points OR a lookback window of ≤ 5ms, THE Inertia_Tracker SHALL set `_INERTIA_STATE["velocity"]` to the zero vector.
3. WHEN `Inertia_Tracker.get_inherited_velocity(half_life=0.16, max_age=0.6, min_speed=50.0)` is called and more than `max_age` seconds have elapsed since the last update, THE Inertia_Tracker SHALL return `None`.
4. WHEN `Inertia_Tracker.get_inherited_velocity(...)` is called and the decayed velocity magnitude is below `min_speed` pixels per second, THE Inertia_Tracker SHALL return `None`.
5. OTHERWISE, THE Inertia_Tracker SHALL return the velocity decayed by `0.5 ** (elapsed / half_life)`.
6. WHEN `OS_Backend.moveTo(..., inertia=True)` is called, THE OS_Backend SHALL pass `Inertia_Tracker.get_inherited_velocity()` to `Trajectory_Builder.build_trajectory(..., initial_velocity=...)`.

### Requirement 5: Movement Profile Knobs

**User Story:** As an existing Activision user, I want to keep the SAFE/FAST/CHAOTIC profile choices and macro-rhythm jitter so that nothing about my current settings UI breaks.

#### Acceptance Criteria

1. THE OS_Backend SHALL continue to read `p.MACRO_PROFILE` and `p.MACRO_RHYTHM` and feed them through `source.utils.profiles.get_macro_profile()` for click/key delays, click/key intervals, and click/key hold durations.
2. WHERE `p.MACRO_RHYTHM` is `True`, THE OS_Backend SHALL invoke `source.utils.profiles.maybe_rhythm_jitter()` between actions and apply the returned pause and (dx, dy) drift via the HID Bridge (drift via `mouse_move_relative`, NOT via `SetCursorPos`).
3. THE Activision `source/utils/profiles.py` SHALL be extended to include `click_hold_median_ms`, `click_hold_iqr_ms`, `click_hold_bounds_ms`, `key_hold_median_ms`, `key_hold_iqr_ms`, and `key_hold_bounds_ms` for each of the SAFE / FAST / CHAOTIC profiles, with values matching Charge-Grinder v3.4.0 `source/utils/profiles.py`.
4. WHEN `OS_Backend.click(...)` performs `mouseDown(...)/mouseUp(...)`, THE OS_Backend SHALL sample the hold duration from a Gaussian with median = `click_hold_median_ms` and σ = `click_hold_iqr_ms / 1.349`, clamped to `click_hold_bounds_ms`.
5. WHEN `OS_Backend.press(...)` performs `key_press` followed by `key_release_all`, THE OS_Backend SHALL sample the hold duration from a Gaussian with median = `key_hold_median_ms` and σ = `key_hold_iqr_ms / 1.349`, clamped to `key_hold_bounds_ms`.

### Requirement 6: 12 New Packs Imported

**User Story:** As a Mirror Dungeon EXTREME runner, I want the new pack list from Charge-Grinder v3.4.0 to be available in Activision's pack picker, so that floors with the new packs are recognized and prioritized correctly.

#### Acceptance Criteria

1. THE Activision `source/utils/paths.py` `PACKS` dict SHALL include the following pack name keys that exist in Charge-Grinder v3.4.0 `PACKS` but are missing from Activision: `CodePurple`, `BearersofWeight`, `Line1Madness`, `BlessedCarnival`, `FairyTale`, `IchthyicOdor`, `CompleteExtermination`, `LaManchaMaster`, `Chachihu`, `MidspringDream2`, `The_BE`.
2. THE Activision `source/utils/paths.py` `PACKS` dict SHALL update the floor tuples for `Line1`, `Line2`, `SEA`, `MiracleinDistrict20`, `TheNoonofViolet`, `FullStoppedbyaBullet`, `FallingFlowers`, and `TheUnconfronting` to match Charge-Grinder v3.4.0 (these are floor remappings tied to the new packs being added).
3. THE Activision SHALL include any `.png` assets for the new pack names under `ImageAssets/UI/` so that `collect_png_paths()` registers them in `PTH` without raising "Duplicate image name" or returning `None` at lookup time.
4. THE Activision `paths.py` SHALL keep the `BANNED` and `HARD_BANNED` lists in sync with the new pack additions, mirroring Charge-Grinder v3.4.0.
5. WHEN `paths.packs_to_floors(PACKS, hard=False)` is called after the update, THE `FLOORS` dict SHALL contain at least one new pack key under each floor that received a new pack.
6. WHEN `paths.packs_to_floors(PACKS, hard=True)` is called after the update and `EXTREME` mode is active (floor 15 lookups), THE `HARD_FLOORS[15]` list SHALL include at least 10 of the 11 new pack names (the release notes call out "10 of which are extreme").
7. WHEN existing Activision team configs that reference only the pre-port pack names are loaded, THE Activision SHALL NOT raise `KeyError`, `IndexError`, or refuse to start (backward-compatible config load).
8. THE Activision `source.pack` module SHALL pick a new pack from the `priority` list when that pack is the only matching pack visible on screen at the relevant floor, just as it does for existing packs.

### Requirement 7: Key-Press Fallback to Mouse

**User Story:** As a user on a Limbus build where keyboard input occasionally drops at the game level, I want the bot to detect failed key presses and fall back to clicking the on-screen target after a few attempts, so that runs do not get stuck mid-floor.

#### Acceptance Criteria

1. THE Activision `source/utils/params.py` SHALL define a module-level integer `KEY_ERRORS` initialized to `0`.
2. THE Activision `source/utils/utils.py` SHALL define a function `input_with_fallback(key, mouse_action, ver_func)` with the same signature as Charge-Grinder v3.4.0.
3. WHEN `input_with_fallback(key, mouse_action, ver_func)` is called and `p.KEY_ERRORS < 3`, THE Input_With_Fallback SHALL invoke the keyboard press for `key` first and return `True` immediately if `ver_func()` returns truthy.
4. IF the keyboard attempt fails (`ver_func()` returns falsy AND `p.KEY_ERRORS < 3` was true at entry), THEN THE Input_With_Fallback SHALL increment `p.KEY_ERRORS` by exactly `1`.
5. WHEN `p.KEY_ERRORS >= 3` at entry OR the keyboard attempt failed during this call, THE Input_With_Fallback SHALL invoke `mouse_action()` and return `True` if `ver_func()` then returns truthy.
6. WHEN both keyboard and mouse attempts fail during the same call, THE Input_With_Fallback SHALL return `False`.
7. IF either `mouse_action` or `ver_func` is not callable, THEN THE Input_With_Fallback SHALL raise `ValueError` with the message `"Pass a way to verify and execute the action!"`.
8. THE Activision `source/move.py` SHALL replace the existing `gui.press(key); enter()` patterns in the unknown-direction, single-direction, and node-search branches with calls to `input_with_fallback(key, lambda: win_click(...), enter)` mirroring the Charge-Grinder v3.4.0 `move.py` integration.
9. WHEN a new bot run starts (Activision `Bot.execute_me(...)` is invoked), THE Activision SHALL reset `p.KEY_ERRORS` to `0` so that one bad run does not permanently force mouse mode.

### Requirement 8: Bridge Capability Compatibility

**User Story:** As a maintainer of the ESP32 firmware variants, I want the new movement and fallback features to work without requiring me to change the firmware sketches, so that existing flashed devices keep working.

#### Acceptance Criteria

1. WHEN movement code calls `mouse_move_relative(dx, dy)` with `(dx, dy)` outside `[-127, 127]`, THE HID Bridge SHALL split the move into multiple in-range packets (existing behavior, must remain unchanged).
2. THE Activision SHALL NOT call any DLL function whose name starts with `cg_` (those belong to Charge-Grinder's `bridge.dll` which is not present in Activision).
3. WHEN `Trajectory_Builder` requests an emit rate higher than what the active HID Bridge can sustain, THE OS_Backend SHALL coalesce intermediate steps so that the achievable per-step latency is respected (i.e., the executor MAY drop intermediate samples, but MUST still emit the final endpoint).
4. WHERE `p.BRIDGE_MODE == "esp32"`, THE OS_Backend SHALL use `ESP32Bridge` and accept its higher per-call latency.
5. WHERE `p.BRIDGE_MODE == "esp32s3"`, THE OS_Backend SHALL use `ESP32S3Bridge` and accept its lower per-call latency.
6. THE Activision `source/utils/bridge/bridge.py` (the `ctypes`-based DLL bridge wrapper) SHALL remain in the repository unchanged BUT SHALL NOT be imported by any code path activated when `p.BRIDGE_MODE` is `"esp32"` or `"esp32s3"`.

### Requirement 9: Cross-Platform Pointer-Speed Note

**User Story:** As a Linux user attempting to run Activision in the future, I want the auto pointer-speed learning to work without Windows-only API calls, so that the Linux port (if and when it lands) can reuse the same logic.

#### Acceptance Criteria

1. THE `source/utils/movement/pointer_gain.py` module SHALL NOT import any module under `ctypes.windll` or any Windows-only library.
2. THE `source/utils/movement/builder.py` and `source/utils/movement/generator.py` modules SHALL only depend on `numpy` and standard library modules (no `cv2`, no `pyautogui`, no `ctypes`).
3. THE `source/utils/movement/inertia.py` module SHALL only depend on `numpy`, `math`, and `time`.
4. WHEN Activision is later launched on a non-Windows platform (out of scope for this port but the code MUST remain portable), THE movement subpackage SHALL load without raising `ImportError` (verifiable by importing it from a stub OS backend).

### Requirement 10: Run-Build Compatibility

**User Story:** As a developer running `run-build-windows.ps1`, I want the build to bundle the new `model.npz` and the movement subpackage so that the produced executable still works.

#### Acceptance Criteria

1. THE Activision build script `run-build-windows.ps1` SHALL include `source/utils/movement/model.npz` as a data file (e.g. via Nuitka `--include-data-files=` flag) so that the compiled executable can locate it at runtime.
2. WHEN the produced executable runs, THE `source.utils.movement.builder` module SHALL resolve `model.npz` via the `__compiled__` branch (which expects `move_assets/model.npz` next to the executable) OR a Nuitka-onefile-extracted path, whichever the build uses.
3. WHEN the source build (`python App.py` from a checkout) runs, THE `source.utils.movement.builder` module SHALL resolve `model.npz` via the path `os.path.join(os.path.dirname(__file__), "model.npz")` relative to `builder.py`.
4. THE `requirements.txt` SHALL NOT add any new third-party dependency beyond what is already declared (`numpy` is already present transitively; if a new dep is unavoidable, it SHALL be added to both `requirements.txt` and any platform-specific requirements file).
