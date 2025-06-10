# Sound Effects for Aiden

This directory contains sound effects used by Aiden to enhance the user experience.

## Sound Effect Files

Place the following sound effect files in this directory:

- `activation.mp3` - Played when Aiden is activated by hotkey
- `startup.mp3` - Played when Aiden starts up
- `success.mp3` - Played when an operation completes successfully
- `error.mp3` - Played when an error occurs
- `processing.mp3` - Played when Aiden is processing a request

You can use any sound files you prefer, as long as they have the correct names and are in MP3 format.

## Sources for Free Sound Effects

If you don't have sound effects, you can find free ones at:

1. [Freesound](https://freesound.org/)
2. [SoundBible](https://soundbible.com/)
3. [Zapsplat](https://www.zapsplat.com/)

## Usage

Sound effects are enabled by default. You can disable them by setting `use_sound_effects` to `false` in the `voice` section of `config.json`.

```json
"voice": {
  "use_sound_effects": false
}
