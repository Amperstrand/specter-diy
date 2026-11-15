# Campaign report (rendered)

- cycles: 232, probes ok/fail: 170/90
- latency s: p50=15.01 p90=15.01 p99=15.01 min=15.0 max=15.01 n=170
  `▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁█████████████████████████`
- injections (fired/recovered/survival):
  - vcc: 3/2 (67%)
  - rst: 3/3 (100%)
  - t1bad: 2/2 (100%)
- heap: 213 samples, free 29696→31904 (drift +2208 bytes)
  `▃▃▃▃▃▃▃▃▃▃▃▃▃▂█▁▁▁▂▂▇▆▇▄▃▇▃▆▂▄▅▅▃▁▂▃▃▁▃▄`
- ops ok/fail: TEST_STATUS=170/90, TEST_BOOT_STATE=26/3, TEST_SCREEN=25/4, TEST_WALLET_SMOKE=5/0, TEST_PIN=2/0
- screen_changes: 7
- recoveries: 12 — [['11:14:36', 'no-ok since 11:10:30'], ['11:45:49', 'no-ok since 11:41:34'], ['11:50:44', 'no-ok since 11:46:29'], ['12:25:37', 'no-ok since 12:21:22'], ['12:37:37', 'no-ok since 12:33:22'], ['12:42:32', 'no-ok since 12:38:17'], ['12:47:18', 'no-ok since 12:43:12'], ['13:23:21', 'no-ok since 13:19:06'], ['13:32:08', 'no-ok since 13:27:16'], ['13:42:43', 'no-ok since 13:38:28'], ['13:48:03', 'no-ok since 13:43:48'], ['14:58:38', 'no-ok since 14:54:23']]

## Timeline
```
08:53:10 injection[vcc] firing

08:54:27 injection[vcc]: RECOVERED

08:54:36 screen-diff: changed=True bbox=(0, 0, 160, 120)

09:38:22 injection[rst] firing

09:39:38 injection[rst]: RECOVERED

09:54:45 screen-diff: changed=True bbox=(0, 0, 160, 120)

10:24:57 injection[t1bad] firing

10:26:13 injection[t1bad]: RECOVERED

10:55:54 screen-diff: changed=True bbox=(0, 0, 160, 120)

11:11:09 injection[vcc] firing

11:13:11 injection[vcc]: RECOVERED

11:14:36 RECOVERY: step 0 console daemon (systemd)

11:45:49 RECOVERY: step 0 console daemon (systemd)

11:50:44 RECOVERY: step 0 console daemon (systemd)

11:51:24 RECOVERY: step 1 adapter usbreset

11:51:49 RECOVERY: step 2 SWD reset run

11:52:49 RECOVERY: step 3 reflash known-good

11:56:29 injection[rst] firing

11:58:30 injection[rst]: RECOVERED

11:58:38 screen-diff: changed=True bbox=(0, 0, 160, 120)

12:25:37 RECOVERY: step 0 console daemon (systemd)

12:37:37 RECOVERY: step 0 console daemon (systemd)

12:42:32 RECOVERY: step 0 console daemon (systemd)

12:43:12 injection[t1bad] firing

12:44:28 injection[t1bad]: RECOVERED

12:47:18 RECOVERY: step 0 console daemon (systemd)

12:58:02 screen-diff: changed=True bbox=(0, 0, 160, 120)

13:23:21 RECOVERY: step 0 console daemon (systemd)

13:24:01 RECOVERY: step 1 adapter usbreset

13:28:41 injection[vcc] firing

13:30:43 injection[vcc]: probe failed twice — --

13:32:08 RECOVERY: step 0 console daemon (systemd)

13:42:43 RECOVERY: step 0 console daemon (systemd)

13:43:23 RECOVERY: step 1 adapter usbreset

13:48:03 RECOVERY: step 0 console daemon (systemd)

13:58:47 screen-diff: changed=True bbox=(0, 0, 160, 120)

14:14:51 injection[rst] firing

14:16:06 injection[rst]: RECOVERED

14:58:38 RECOVERY: step 0 console daemon (systemd)

14:59:27 screen-diff: changed=True bbox=(0, 0, 160, 120)

15:00:54 injection[t1bad] firing

15:02:09 injection[t1bad]: RECOVERED

15:04:59 RECOVERY: step 0 console daemon (systemd)

15:46:56 injection[vcc] firing

15:48:13 injection[vcc]: RECOVERED

```
