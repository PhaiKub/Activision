# Requirements Document

## Introduction

This feature ports and adapts the upstream Charge-Grinder v3.4.0 release into the Activision fork, which uses an ESP32 HID hardware bridge for input injection instead of OS-level synthetic input. The port covers four upstream changes:

1. A new mouse movement model trained on real human Mortal Difficulty (MD) speedrun data, intended to emulate human movement distributions for anti-heuristic-detection purposes.
2. Auto-detection and adjustment of OS pointer speed (already supported on Windows; new at-runtime calibration on Linux because programmatic pointer-speed control is unreliable across Linux distributions).
3. Twelve new content packs (ten of which are Extreme difficulty) added to the pack catalog.
4. A fallback path that switches to mouse-driven inputs after repeated key-press failures, because the game does not always register key inputs reliably.

All changes MUST remain compatible with the existing ESP32 USB HID bridge (`esp32s3` mode) and ESP32 BLE/WiFi HID bridge (`esp32` mode) defined in `source/utils/bridge/`, and MUST NOT regress existing Windows-only macro flows.

## Glossary

- **Bot**: The Activision fork's automation engine, rooted in `Bot.py` and `source/`.
- **App**: The PySide6 GUI in `App.py` and `source_app/`.
- **Bridge**: The HID transport layer in `source/utils/bridge/` (`esp32_bridge.py`, `esp32s3_bridge.py`) used to send mouse and key events to the game over real HID hardware.
- **OS_Backend**: The OS-specific input/window backend. Today only `source/utils/os_windows_backend.py` exists; this feature introduces a Linux counterpart for pointer-speed calibration.
- **Movement_Model**: The mouse trajectory generator that produces a sequence of cursor positions and per-step delays from a start point to a target point.
- **MD_Trajectory_Dataset**: The dataset of recorded human Mortal Difficulty speedrun mouse trajectories distributed with Charge-Grinder v3.4.0, used to parameterize Movement_Model.
- **Macro_Speed_Multiplier**: A scalar applied on top of the dataset's natural speed distribution. Per upstream design it is approximately 1.20 (≈20% faster than recorded human runs) and SHALL NOT exceed an upper bound that distorts the source distribution.
- **Pointer_Speed**: The OS pointer-speed (acceleration curve and sensitivity) setting that affects how raw mouse-delta HID events translate to on-screen cursor movement.
- **Pointer_Calibrator**: The component that measures or sets Pointer_Speed at runtime so Movement_Model output produces the intended on-screen distance.
- **Mouse_Acceleration**: The non-linear OS pointer ballistics curve (e.g. Windows "Enhance pointer precision"). Distinct from Pointer_Speed; cannot be modeled reliably and MUST be disabled by the user.
- **Pack_Catalog**: The pack definitions and floor mappings in `source/utils/paths.py` (`PACKS`, `FLOORS`, `HARD_FLOORS`).
- **Extreme_Mode**: The difficulty enabled by `p.EXTREME`, which extends floor range to 1–15 and uses the floor-15 pack list.
- **Key_Fallback_Mode**: A runtime state in which the Bot, after detecting repeated key-press failures, substitutes mouse-input alternatives for actions that would otherwise use keys.
- **Key_Failure**: A single attempted key press that is not registered by the game, detected by absence of the expected post-press UI state within a bounded time window.
- **Key_Failure_Threshold**: The configurable count of consecutive Key_Failure events that triggers entry into Key_Fallback_Mode. Default value: 3.

## Requirements

### Requirement 1: Adopt Human-Emulation Mouse Movement Model

**User Story:** As a Bot operator, I want mouse movement to mimic the distribution of real human MD speedrun trajectories, so that automated input is harder to distinguish from human input by anti-cheat heuristics.

#### Acceptance Criteria

1. THE Movement_Model SHALL generate cursor trajectories whose per-segment speed and curvature are sampled from MD_Trajectory_Dataset.
2. WHEN the Bot requests a move from point A to point B, THE Movement_Model SHALL produce a sequence of intermediate positions and delays that terminate at point B within a 2-pixel endpoint tolerance.
3. THE Movement_Model SHALL apply Macro_Speed_Multiplier to the sampled trajectory's total duration, where Macro_Speed_Multiplier is configurable and SHALL default to 1.20.
4. THE Movement_Model SHALL reject Macro_Speed_Multiplier values greater than 1.50, because higher values distort the source distribution beyond the upstream design intent.
5. WHEN Movement_Model generates a trajectory, THE Bot SHALL emit each intermediate position via the active Bridge (`esp32` or `esp32s3` mode) using the same call surface currently used by `source/utils/os_windows_backend.py:moveTo`.
6. WHEN Movement_Model is active, THE Bot SHALL preserve the existing HID-position-sync step (the `+1/-1` nudge in `_sync_hid_position`) so the game registers the final absolute cursor position.
7. WHERE the user has selected a macro profile in `source/utils/profiles.py` (`SAFE`, `FAST`, or `CHAOTIC`), THE Movement_Model SHALL combine profile jitter (`endpoint_jitter_px`, `noise`, `mouse_velocity`) with MD_Trajectory_Dataset sampling, with profile values acting as multipliers rather than overriding the dataset distribution.
8. THE Movement_Model SHALL be packaged as a standalone module under `source/utils/` so it can be unit tested without requiring an active Bridge connection.
9. WHEN MD_Trajectory_Dataset cannot be loaded at startup, THEN THE Bot SHALL log an error identifying the missing dataset path and SHALL fall back to the existing `easeInOutQuad` trajectory generator without aborting startup.
10. FOR ALL trajectories produced by Movement_Model, the trajectory generation function SHALL be deterministic given a fixed random seed (round-trip property: same seed produces same trajectory sequence) so movement behavior can be reproduced in tests.

### Requirement 2: Pointer Speed Auto-Adjustment (Windows)

**User Story:** As a Windows Bot operator, I want the Bot to set Pointer_Speed to a known value before a run and restore it on exit, so that Movement_Model's output produces the intended on-screen distance.

#### Acceptance Criteria

1. WHEN the Bot starts a run on Windows, THE Pointer_Calibrator SHALL set Windows Pointer_Speed to the upstream-defined target value via `SystemParametersInfoW(SPI_SETMOUSESPEED, ...)`.
2. THE Pointer_Calibrator SHALL record the prior Pointer_Speed value before changing it.
3. WHEN the Bot stops, pauses to another window, or is closed, THE Pointer_Calibrator SHALL restore the prior Pointer_Speed value, consistent with the existing `restore_mouse_settings` invocation pattern in `source/utils/utils.py`.
4. IF the call to set Pointer_Speed returns failure, THEN THE Pointer_Calibrator SHALL log a warning identifying the failure code and SHALL continue execution using the unchanged Pointer_Speed.
5. THE Pointer_Calibrator SHALL detect whether Mouse_Acceleration ("Enhance pointer precision") is enabled and SHALL warn the user via the existing `p.WARNING` channel that Mouse_Acceleration must be disabled for accurate movement.

### Requirement 3: Pointer Speed Auto-Calibration (Linux)

**User Story:** As a Linux Bot operator, I want the Bot to learn the actual Pointer_Speed at runtime, so that mouse movement produces the intended on-screen distance without requiring me to configure pointer speed manually across distributions.

#### Acceptance Criteria

1. WHEN the Bot starts on Linux, THE Pointer_Calibrator SHALL perform a calibration sequence that issues a known relative-motion HID command via the active Bridge and measures the resulting on-screen cursor displacement.
2. THE Pointer_Calibrator SHALL compute a calibration ratio defined as (measured on-screen pixels) divided by (commanded relative HID units) and SHALL store this ratio in `source/utils/params.py` as `POINTER_RATIO`.
3. WHEN Movement_Model emits a trajectory on Linux, THE Bot SHALL scale relative-motion HID commands by the inverse of POINTER_RATIO so that the on-screen path matches the trajectory in pixels.
4. THE Pointer_Calibrator SHALL repeat the calibration sequence at least 3 times and SHALL use the median calibration ratio to reduce sampling noise.
5. IF the standard deviation of calibration samples exceeds 15% of the median, THEN THE Pointer_Calibrator SHALL log a warning and SHALL re-run calibration up to 2 additional times before accepting the median value.
6. THE Pointer_Calibrator SHALL warn the user via `p.WARNING` that Mouse_Acceleration must be disabled, because acceleration cannot be modeled reliably and will invalidate POINTER_RATIO at non-baseline movement speeds.
7. THE Pointer_Calibrator SHALL not attempt to set Linux Pointer_Speed programmatically, because cross-distribution programmatic control is unreliable.
8. WHERE the Linux Bot is started but the platform check determines the OS is not Linux, THE Pointer_Calibrator SHALL skip Linux calibration and SHALL use the Windows path defined in Requirement 2.
9. THE Linux backend SHALL expose the same call surface (`moveTo`, `click`, `mouseDown`, `mouseUp`, `press`, `hotkey`, `screenshot`, `getActiveWindowTitle`, `set_window`, `restore_mouse_settings`) as `source/utils/os_windows_backend.py` so the rest of the Bot is platform-agnostic.

### Requirement 4: Add 12 New Packs to Pack_Catalog

**User Story:** As a Bot operator, I want the v3.4.0 pack additions available in the catalog, so that pack selection logic can recognize and route them on the correct floors.

#### Acceptance Criteria

1. THE Pack_Catalog SHALL include the 12 new packs introduced in Charge-Grinder v3.4.0, with 10 packs assigned to Extreme_Mode floor 15 and 2 packs assigned to floors per upstream definitions.
2. WHEN a pack is added to `PACKS` in `source/utils/paths.py`, THE Bot SHALL also include a corresponding template image under `ImageAssets/UI/pack/` keyed by the pack's exact name (matching `PTH[pack_name]` lookup in `source/pack.py`).
3. THE Bot SHALL ensure each new pack name is unique across `PACKS` and produces no `Duplicate image name detected` error from `collect_png_paths` in `source/utils/paths.py`.
4. WHEN a new Extreme_Mode pack is selectable on floor 15, THE pack-evaluation logic in `source/pack.py` SHALL match it via SIFT against `ImageAssets/UI/pack/` without changes to the matching algorithm itself.
5. THE Pack_Catalog SHALL update `BANNED` and `HARD_BANNED` lists if any of the 12 new packs are upstream-classified as suboptimal, mirroring the upstream v3.4.0 classification.
6. WHEN the user selects priority or avoid lists in the App for the new packs, THE App SHALL persist these selections through `source_app/settings_manager.py` using the same schema as existing packs, requiring no settings-file migration step.
7. FOR ALL entries in `PACKS`, the value tuple SHALL contain exactly two sub-tuples representing (normal_floors, hard_floors), preserving the existing `packs_to_floors` contract.

### Requirement 5: Key-Press Failure Fallback to Mouse Input

**User Story:** As a Bot operator, I want the Bot to switch to mouse-only inputs after key presses repeatedly fail to register, so that runs continue successfully when the game ignores keyboard inputs.

#### Acceptance Criteria

1. WHEN the Bot performs a key press that has a verifiable post-press UI state, THE Bot SHALL verify the expected state within 1.5 seconds.
2. IF the expected post-press UI state is not observed within 1.5 seconds, THEN THE Bot SHALL record one Key_Failure event for the affected key.
3. WHEN consecutive Key_Failure events for the same logical action reach Key_Failure_Threshold, THE Bot SHALL enter Key_Fallback_Mode for that action and SHALL log entry into Key_Fallback_Mode at INFO level.
4. WHILE Key_Fallback_Mode is active for an action, THE Bot SHALL replace the key press with the equivalent mouse-driven UI interaction (for example, clicking the on-screen button instead of pressing `space` to confirm).
5. THE Bot SHALL maintain a mapping from key-driven actions to their mouse-driven equivalents; only actions present in this mapping SHALL be eligible for Key_Fallback_Mode.
6. IF a key-driven action has no defined mouse equivalent in the mapping, THEN THE Bot SHALL log an error and SHALL raise a RuntimeError to be handled by the existing `handle_fuckup` recovery path.
7. WHEN a Bot run completes, fails, or is paused, THE Bot SHALL reset all Key_Failure counters and Key_Fallback_Mode state to default.
8. THE Bot SHALL expose Key_Failure_Threshold as a configurable parameter in `source/utils/params.py` with a default value of 3.
9. WHEN Key_Fallback_Mode is active, THE Bot SHALL still attempt the key press once per affected action periodically (no more than once per minute) to detect recovery, and SHALL exit Key_Fallback_Mode for that action upon a successful key press verification.

### Requirement 6: Bridge Compatibility for ESP32 HID Hardware

**User Story:** As a Bot operator using ESP32 HID hardware, I want all v3.4.0 changes to work with both `esp32` (BLE/WiFi) and `esp32s3` (USB HID) bridge modes, so that I do not need different builds for different hardware.

#### Acceptance Criteria

1. THE Movement_Model SHALL emit movements using only the public API of the active Bridge (`mouse_press`, `mouse_release`, `mouse_move_relative`, `mouse_scroll`, `key_press`, `key_release_all`, `key_multi_press`) as currently defined for both `esp32_bridge.py` and `esp32s3_bridge.py`.
2. WHEN `BRIDGE_MODE` in `source/utils/params.py` is `esp32s3`, THE Bot SHALL produce the same logical input sequence as when `BRIDGE_MODE` is `esp32`, with timing differences absorbed by the Bridge implementation rather than the Movement_Model.
3. WHEN Pointer_Calibrator runs on Linux, THE Pointer_Calibrator SHALL issue calibration HID commands through the active Bridge rather than the OS, so calibration measures the true HID-to-pixel ratio for the connected hardware.
4. WHEN Key_Fallback_Mode triggers a mouse click, THE click SHALL be delivered through the active Bridge using the same `mouseDown`/`mouseUp` path defined in `source/utils/os_windows_backend.py`.
5. IF a Bridge command raises an exception during Movement_Model execution, THEN THE Bot SHALL retry up to 3 times with a 50 ms delay between retries, consistent with the existing `mouseUp` retry pattern, before propagating the exception.

### Requirement 7: Movement Model Determinism and Round-Trip Property

**User Story:** As a developer, I want Movement_Model trajectory generation to be reproducible from a seed, so that I can write property-based tests that verify movement behavior across input distributions.

#### Acceptance Criteria

1. THE Movement_Model SHALL accept an optional random seed parameter and SHALL produce identical trajectories for identical (start, end, seed, profile, multiplier) tuples.
2. FOR ALL valid (start, end) pairs within the 1920×1080 logical coordinate space, the trajectory SHALL start within 1 pixel of the start point and end within 2 pixels of the end point (endpoint preservation invariant).
3. FOR ALL trajectories produced, the cumulative duration SHALL be greater than 0 and SHALL be less than 10 seconds for moves of any distance up to the screen diagonal (≈2203 pixels), to bound test execution time.
4. WHEN the trajectory generator is invoked with `start == end`, THE Movement_Model SHALL return a single-position trajectory whose duration is 0 (degenerate-case invariant).
5. FOR ALL trajectories, every intermediate position SHALL be strictly inside the bounding box defined by the start and end points expanded by `endpoint_jitter_px + noise` margin, so trajectories do not wander arbitrarily far from the direct path.

### Requirement 8: Logging and Telemetry for v3.4.0 Behaviors

**User Story:** As a Bot operator, I want clear log entries when v3.4.0 behaviors activate, so that I can diagnose issues such as failed calibration, missing datasets, or fallback activation.

#### Acceptance Criteria

1. WHEN the Movement_Model successfully loads MD_Trajectory_Dataset, THE Bot SHALL log the dataset version and sample count at INFO level once per Bot startup.
2. WHEN Pointer_Calibrator completes calibration on Linux, THE Bot SHALL log the chosen POINTER_RATIO and sample standard deviation at INFO level.
3. WHEN the Bot enters Key_Fallback_Mode for an action, THE Bot SHALL log the action name and consecutive Key_Failure count at INFO level.
4. WHEN the Bot exits Key_Fallback_Mode for an action after a successful recovery key press, THE Bot SHALL log the action name at INFO level.
5. THE Bot SHALL route all v3.4.0 log entries through the existing `logging` channel configured in `source/utils/log_config.py`, so users do not need a new log destination.
