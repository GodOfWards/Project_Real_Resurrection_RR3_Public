# Installing a patched APK (summary)

How to get a patched library onto the phone. Detailed version (every
command explained, troubleshooting): [details/installing-details.md](details/installing-details.md) (every detailed doc is in [`details/`](details/)).

Based on the latest `develified.apk` from the
[Project Real Resurrection Discord](https://discord.com/invite/project-resurrection-official-server-1482888689854971997)
(Mali GPU variant).

> **Project Real Resurrection.** Part of Project Real Resurrection's work on Real
> Racing 3. Not affiliated with, endorsed or supported by Electronic Arts.

## What to know

- The patched APK is signed with **your own key**, so the first time it
  can't install over the original `develified.apk`: you back up, uninstall,
  install, and restore once.
- After that, every build signed with the **same key** installs as a normal
  update and keeps your data. Keep `key.pk8` and `cert.pem` safe.
- Use the `files` game data that matches your APK's GPU variant.

## Steps

1. Get the library ([getting-files.md](getting-files.md)) and patch it
   ([patched-library.md](patched-library.md)).
2. In Termux: put it into a copy of `develified.apk` at
   `lib/arm64-v8a/`, align and sign it (commands in
   [details/installing-details.md](details/installing-details.md#1-build-the-patched-apk-termux)).
   A build that talks to an http server (a Tailscale or local test server)
   also needs the `rr3_cleartext.py` lines marked `# http` there, or the
   game sends nothing to the server.
3. First time: back up `Android/data/com.ea.games.r3_row`, uninstall the
   game, install the new APK, open it once and close it, delete its `files`
   folder, copy your backed-up `files` folder back. Then run the
   [doc-folder fix](rish-guide.md#part-2-save-copies-are-0-bytes--permission-denied), or the save can't be copied out
   after the game's next save.
4. Later builds with the same key: open the APK and tap **Update**.
5. A test build signed with someone else's key ("package conflict"):
   re-sign the whole APK with your key, see
   [details/installing-details.md](details/installing-details.md#4-re-sign-someone-elses-apk-test-builds).
6. Crashes: [crash-logs.md](crash-logs.md).

Copy-paste versions of these commands, with the version and build as
variables: [commands.md](commands.md).

---

Detailed version: [details/installing-details.md](details/installing-details.md). Every detailed doc is in
[`details/`](details/).
