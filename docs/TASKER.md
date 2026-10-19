# Tasker bridge

Digitomancy fires Tasker tasks with an adb broadcast:

```
am broadcast -a cc.madness.digitomancy.RUN --es task "<Task Name>" --es par1 … --es dgm_id <id>
```

## Phone-side setup (one time)

1. **Profile:** Event → System → **Intent Received**
   - Action: `cc.madness.digitomancy.RUN`
2. **Task "DGM Dispatch"**, attached to that profile:
   - Perform Task: name `%task`, Parameter 1 `%par1`, Parameter 2 `%par2`
3. **Optional result channel.** At the end of a task that should answer back:
   - If `%dgm_id` is set, Write File `Download/digitomancy/%dgm_id.json` with the JSON result.
   - `dgm tasker TASK -w 10` polls for that file, reads it, and deletes it.

Tasker makes each intent extra available as a local variable with a lowercase name (`--es par1 x` becomes `%par1`).

**Unverified:** this hasn't been tested end to end on a device yet. Try it first with a harmless task, such as one that shows a Flash.

## When to use which

- **Use a Tasker task** for anything Tasker already does well: system toggles, intents, plugins, AutoInput, MQTT.
- **Use a Digitomancy routine** when you need to see the screen: UI-tree checkpoints, image matching, or an agent recovering from an unexpected state.
- **Combine them:** a routine can call `ctx.tasker("Task")` in the middle of a flow.

## Hazard guard

The bridge refuses to fire a task when any of these match:
- its name contains a built-in hazard word (door, unlock, garage, gate, …),
- its name matches a line in `catalog/hazard_patterns.txt` (your own place or device names),
- it's listed in `catalog/hazards_manual.txt` (tasks seen on the phone but not exported yet),
- the catalog (`dgm catalog`) flags it, directly or because it calls a hazard task.

Pass `allow_hazard=True` only for a specific task you mean to run.
