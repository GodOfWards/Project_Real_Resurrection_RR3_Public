#!/usr/bin/env python3
"""Cloudcell server for Real Racing 3: records the sync requests the game
sends and, with --answer, answers leaderboards, race results and ghosts.

For a lib made with rr3_cc_local.py, which sends the game's Cloudcell sync
requests (leaderboards and the rest) to http://HOST:PORT/CC_Sync.php
(default 127.0.0.1:8080). Runs on the phone (Termux) or on a PC
(--bind 0.0.0.0). Guides: docs/cloudcell-test-server.md (phone),
docs/community-leaderboard-server.md (shared server).

One line is printed per request. With --save every request is also
saved in --out (default: logs/ next to this script) as
  NNNN-METHOD-path.bin   the request body, exactly as received
  NNNN-METHOD-path.txt   time, method, path, headers, body size, first bytes
Saving is off by default since v5.1 (the bodies and headers hold phone
ids); turn it on only for your own tests (--no-save is still accepted
and changes nothing). A request the
server does not answer gets an empty body with --status (default 503,
"unavailable"), so the game sees a failed sync just as it does today.

With --answer (format: docs/details/cloudcell-sync-format.md; needs
rr3_cc_blob.py in the same folder), the server answers the leaderboard
(LeaderBoardSync 10477, one group band for LeaderBoardGroupSync 10484, v5.30),
race results (10451), ghosts (10695, 10694, 10696, 10476), Ghost Challenge
rows (10516), mail (10459), friends' results (10419) and social friends
(10556, v5.16), and since v5.24 acknowledges StatManager's game sessions
(68: status 1, the stats are not kept). Requests with
none of these still get --status.

Server time (v5.14, issue #197; POST too since v5.36, the game sends POST):
GET or POST /time is always answered with 200, an empty body and the header X-Request-Start: <Unix time in seconds>, which
the game takes as the server time. A lib needs rr3_cc_local.py sync v2 to
send /time here (v1 sends it to https on 443).

Real times: the game uploads every finished race with subsync 10451
(UploadResultTask) and keeps it queued until a server accepts it; with no
server, Tom's queue had grown to 155 results. The server stores every Time
Trial result from it, keeps the best time per event in --times, accepts
the upload so the game empties its queue, and answers the leaderboard of
an event with the stored times of every player, with --tag.
--skip-queued accepts each player's first upload without storing it when
it holds more than one result (old queued results). An event with no
stored time gets no rows (v5.30; before, five test rows "Driver 1".."5").
Each leaderboard (10477) and group list (10484) of a request is answered
for its own event (v5.30).

Players: each request is matched to a player key, an HMAC of the phone's
Android id from the request header (Synergy id if there is none) made
with the secret in --server-key (player_key()). The key file is created
on the first start with --answer; keep it private and back it up: with a
new one every player starts over (new member id, no times or ghosts).
Names come from --names (keyed by Android id, Synergy id or player key),
else the player's in-game username (a lib patched with rr3_username.py
sends it in the request header; kept per player in --usernames), else
--name, else "Racer" + the player key's last 4 characters. Each player
gets a member id (from 1000, in order, never reused; kept in --members),
sent in the reply and in their leaderboard rows (i18); ghosts are keyed
by it (issue #95).

Ghosts (issue #94; upload and Watch Replay confirmed in game with b30):
after each Time Trial the game asks for an upload slot (10695), PUTs the
ghost file to the URL in the reply (http://<Host header>/ghost/<key>, or
--ghost-url), then links it (10694: event, lap time, car). The server
keeps the fastest ghost per member id and event in --ghosts and sends it
back inline when a phone asks for it (10476: Watch Replay, or your own
ghost after a reinstall). Since v5.6 it also answers 10516, the rows Ghost
Challenge asks for first (you and the rival, by member id). Since v5.42
every ghost is validated first (analysis/ghost-files.md 4): the game's
reader trusts the file, so only well-formed files that match the link are
kept and sent.

Cloud save (v5.63-v5.73, issue #501, analysis/cloud-save.md; upload tested
in game with v5.64, restore with v5.65; off unless --cloud-save): the upload slot (10660) gets
status 0 (0 = go on; v5.63 sent 1, a failure for the game), a
one-use key and <--ghost-url or http://Host>/save/<key>; the save PUT
there (up to --cloud-save-max-bytes, 9 MB) is kept as received in
--cloud-save-dir/<member>/ (the --cloud-save-versions newest, 3); 10661
gets 1; a corrupt-save report (22) is kept in <member>/corrupt/. List (47)
gets an empty list (u32 0, 0, 0; v5.64), except for the members in
--cloud-save-restore FILE (v5.65, #514): one row offering their newest
version and a one-use GET /save/<key>; the version sent is pinned (kept
apart from the rotation). Since v5.70 a version is offered and sent only
if it passes four checks (md5, blob checksum, full unpack, the bundle with
a valid character.2.dat); a failing one is skipped and logged. Since
v5.72 (#530, --cloud-save-presets FILE; not tested in game) the site's
Cloud save page lets a logged-in member put one of our preset
character.2.dat files in their cloud saves (twice a day; opts them in) and
go back to their last own save, which is kept meanwhile. Since v5.73,
--cloud-save-restore-all gives every member (not iOS builds yet) restores
of their own saves. Download by 48 is not
answered; 10555 is never answered (0 deletes
the player's progress).

Mail (v5.6, analysis/leaderboard-ghosts.md section 7; not tested in game):
when a new best passes another player's best on an event, the server keeps
a "someone beat your time" mail for that player in --mail (at most 20 per
player, 30 days; one new best mails at most the 20 fastest players it
passed, since v5.9). The game asks for mail with 10459 (from the event map,
at most every 15 minutes) and the time of its last check; the server sends
the newer ones. Tapping the mail opens Ghost Challenge against the
player who beat you.

Friends' results (v5.7, analysis/friends.md, issue #163; not tested in
game): the phone keeps a mail only for events in its friends list, which
only the reply to 10419 fills. The server answers each event a 10419 asks
for with the player's friends' rows (none before v5.16), which still gives the event
its friends entry and res_<event>.pld on the phone, so a later mail for it
should be kept. The phone sends 10419 only now and then (after some
races, for some event cards; analysis/friends.md section 2).

Friends and the website login (v5.16, issue #218; design: issue #163;
not tested in game). A lib with the secret patch sends "rrsecret:" + 64 hex
(32 random bytes made on the phone) in every request header; the server
keeps the first secret per player in --secrets (mode 0600) and ignores a
different one later. The game's login entry opens
https://<host>/prr/login?v=1&m=<member>&c=<code> in the in-game browser:
code = the first 16 bytes, as hex, of HMAC-SHA256(secret, b"login" + u32
member + u64 (Unix time // 60)), little-endian; the current minute and one
on each side are accepted, each code once (v5.17: a used code is no failed
try, and a player still logged in goes to /prr/), and after 5 wrong codes a player
waits 15 minutes (20 wrong codes per IP an hour). A good code sets the
cookie prr_session (Path=/prr/, Secure, HttpOnly, SameSite=Lax; kept in
memory, at most 12 h) and redirects to /prr/; the friends page there
(tools/prr_site/index.html) calls the API under /prr/api/: me, friends,
search?q= (GET); request, accept, reject, cancel, remove {"member": n},
logout, logout-all (POST with the header X-PRR: 1). At most 20 requests
sent a day and 100 friends plus pending requests per player. Friends are
kept in --friends; they fill the rows of 10419 (each friend's stored time
on the event) and the answer to 10556 (the friends' member ids, the
"social friends" sync the game sends once logged in). Behind a reverse
proxy the client address for the limits is CF-Connecting-IP or the first
X-Forwarded-For, trusted only for requests from this machine. /prr/
requests are never saved with --save (the URL and cookie log a player in).
Since v5.44 every /prr/ answer says Content-Security-Policy: frame-ancestors
'none' and X-Frame-Options: DENY: the site can't be framed (#359).
Since v5.26 the friends leaderboard tab (10486) gets the asking player's
friends' rows for the event (v5.27: not the player's own; the game adds it) (analysis/social-login.md 5.2).
OMP invites (v5.56, issue #427): see OmpInvites; the host's 10455 is kept
when MP made the room for that host and the invitee is a PRR friend; the
invitee gets a news popup at the next game start and the link through
GET /prr/api/me/invites; matches of an invite group are private (unranked).
Race Selector P2P (v5.60, issue #469): see OmpSelectorRooms; a StartMatch
from the members of a selector room rr3_mp_server.py v0.26 locked gets
that room's track and laps instead of the rotation's, and the match is
kept with "selector": true (unranked, no league unlock).
Since v5.53 the friends' details sync (10472, sent by rr3_prr_social.py
v2 phones) gets one record per PRR friend: name, member id, and the stats
and owned cars that friend's own 10472 sent (kept in --friend-details);
they fill the game's friends screens and "N friends own this car"
(analysis/social-login.md 9.2, issue #278). Since v5.54 the request is
read with its real 26 stats and the reply carries 27: the friend's own
words 1-24, their number of friends, words 25-26 (9.9).

A changed phone secret (v5.54, issue #423): the first secret stays kept,
but the newest different one is remembered (in memory) and logged once
per run. A wrong login code made with it is logged as "wrong code (phone's
secret changed <time>)", redirects with &reason=secret-changed, and files
a reset request in --secret-reset-requests (member, the new secret, when
it was first seen, when and from which IP the login was tried). The admin
checks with the player and adds the member id to --secret-resets: an open
request's secret is then kept at once. List open requests with
  python3 -c "import json; [print(m, v['asked'], v['ip']) for m, v in json.load(open('data/rr3-secret-reset-requests.json')).items()]"

OMP results (v5.47, issues #360, #359): StartMatch opens a match in
--omp-matches (default data/rr3-omp-matches.json, reloaded at start);
each FinishedMatch is kept as its sender's report (only when the sender's
own row is the asking member) and still answered at once. A match is
settled when every starter has reported, or 5 min after its first report
with a finished player (v5.82), at the latest laps x 5 min (10..60 min,
v5.78) after its start (checked on every request and every 15 s): a
player's own report sets their status and time, else the most common
value from the other phones (a tie: the first report's); not reported =
DNF; a time <= 0, below laps x 30 s (v5.82) or above laps x 10 min = no
time, DNF;
positions are the server's (finished by the phone's position, then time
(v5.49), then the rest). One record
per race is appended to --omp-results (default data/rr3-omp-results.jsonl,
never rewritten), loaded at start. Public read-only API (no cookie):
/prr/api/matches?before=&limit=, match/<id>, player/<pid>/matches,
players?q=; answers give the race date only, never member ids, and send
Cache-Control: max-age=30 and X-Robots-Tag: noindex; 120 a minute per IP.
/prr/api/me/matches needs the cookie (your member id, pid and full times).
pid = first 12 hex of HMAC-SHA256(server key, b"pid" + u32 member).
Names: current name; "Guest" without a member; "Player" for a shadowed
player or one in --public-hidden (default data/public-hidden.txt,
`member N` per line, re-read when it changes).
Live status (v5.68, #522): /prr/api/live (no cookie, max-age=15, the same
per-IP limit) = players online (a game request in the last 5 min, memory
only), players racing and the rooms racing now (open matches with a
StartMatch: league, track, laps, players, minutes; invite and Race
Selector rooms only as "private"); no ids or timestamps. The log
says "live: online N, racing M, rooms K, lobby L" once a minute.
v5.71 (#542): live also lists the rooms waiting in MP's lobby (--mp-status,
rr3_mp_server.py v0.28's status file, ignored when older than 60 s) and
the names in public rooms ("Player N" for --public-hidden players; private
rooms never). /prr/api/top = Top 10 wins / podiums / races finished
(public rooms, all-time, max-age=60). /prr/api/status (#374) = counts:
online in 5 min / 1 h, players and races today (UTC), MP's rooms;
v5.77: registered (member ids given out, a number only).
Ratings (v5.79, #263): --ratings off|shadow|on (default off) and
--ratings-start YYYY-MM-DD. A public room is rated when it settles, from
its players' ratings when it opened (iRating-style Elo, K 32, floor 100,
everyone starts at 1000; quorum: finishers > starters / 2, then DNF /
left are tied last; without a quorum only a player who left loses, to
every finisher). shadow = into --ratings-shadow-file (+ .jsonl room log)
only, never sent or shown; on = --ratings-file, the FinishedMatch rows
and /prr/api/ratings?limit=&offset= (no cookie; {"ranked": false,
"starts"} while not on). shadow turns on by itself at 00:00 UTC on
--ratings-start. Invite and Race Selector rooms are never rated.
--ratings-report FILE prints the top / bottom and largest swings.

Blocklist (v5.37, issue #332): --blocklist (default data/blocklist.txt),
one rule per line, `member N` or `ip A.B.C.D` / `ip A.B.C.0/24`, `#` for
the reason; re-read when it changes (no restart), a missing file blocks
nobody. A blocked address gets 403 on every request (behind Caddy the
forwarded client address counts); a blocked member gets 403 on syncs and
ghost uploads, and can't log in or use the friends site. Nothing they
send is stored. Since v5.80 their stored times are also hidden, as
with --lb-banned.

Leaderboard ban (v5.80, issue #607, docs/lb-ban.md): --lb-banned (default
data/lb-banned.txt), `member N` per line, `#` for the reason, re-read
when it changes (no restart). A shadow ban: the member plays as before
and sees their own times; their PRR friends still see them in the
friends tabs (10486, 10419), rival rows (10516), ghosts and mail; for
everyone else their rows (10477), band counts (10484), ghosts and mail
are gone, the site shows them as "Player" (no player page) and leaves
them out of Top 10 and the ratings board, and they get no WTT prize.
Reversible: nothing stored is changed. --lb-banned-report prints each
banned member's stored times, ghosts, races and prizes (read-only).

Held results (v5.84, issue #606, docs/cheat-detection.md): a new Time
Trial best that breaks a rule is stored "held": its owner sees it, others
keep seeing the owner's previous best (or nothing), no mail, no WTT prize
until released. Rules: t1 a WTT time outside the WTT's week + 6 h
(--prize-events); t2 more than 7% under the fastest other visible time on
an event with 5+ visible entries (re-checked whenever that event changes,
released when the field catches up); t4 a WTT time without a ghost of
that lap (released when the ghost comes); t6 a WTT PR off the event's
usual PR for the car (3+ others with it). An admin approves or rejects a
held time with a line in --lb-banned (`approve member N event E time T`,
`reject ...`: the time is dropped and the previous best comes back), on
the site's Admin tab (members in --lb-admins) or bans the member.
--held-report prints every held time with the lines (read-only).
--lb-testers (`member N`): testers' times are seen by them and their
friends only, no WTT prize. --no-lb-holds turns the rules off. OMP (#606):
a room's only finisher whose opponents all left or did not finish "won by
forfeit" (no time on the site); a finisher whose own time differs from
another phone's view of it by more than 1 s, or whose finish report came
more than 3 min after start + time, is "disputed" in the record, logged and
never rated.

Key attestation (v5.38, issue #204; rr3_attest.py, docs/key-attestation.md):
with --answer and the cryptography package, GET /prr/attest/challenge
gives the phone a nonce and POST /prr/attest takes its certificate chain
({"v": 1, "nonce", "android_id", "chain": [base64 DER, leaf first]}). A
proof that verifies to Google's roots, with the challenge SHA-256(nonce ||
the player's rrsecret), a TEE or StrongBox key and the app signed by a
--trusted-sigs key, marks the player attested for 24 h. Every sync's log
line then says "att devel (tee, locked)", "att fail (reason)" or "att
none". Log only, unless --attest-enforce (v5.57, issue #452): then a sync
from a player without a passing proof in the last 24 h gets 403 ("att none
denied"). The refused sync's rrsecret is kept in memory for a player with
no kept secret, so the proof the same sync starts on the phone can be
checked; /prr/attest answers 503 while there is no secret at all (the
phone tries again). --attest-enforce without working attestation stops at
start. --attest-ios-exempt (v5.59, issue #451) still answers iPhones, which
can't attest yet: an IDFV, a player secret and an allowed iOS build label
("att none (ios exempt)"; v5.61: an Android or Synergy id read from an
iPhone's header no longer blocks it, and a refused iOS sync logs why); it
needs --attest-enforce and --build-allowlist. --no-attest turns it off; without cryptography the start line says
"attestation disabled" and the endpoints answer 503.
Attestation tokens (v5.58, issue #452): a passing proof's answer is
{"ok": true, "token": "v1.<payload>.<mac>"}; another server (devel's asset
server) sends the phone's token to POST /prr/api/att/check with the
X-PRR-Admin secret and gets 200 {"ok": true, "member", "build", "level",
"signer", "exp"} or 403 {"ok": false, "reason"}. Keys: --att-token-key
(data/prr-att.key), --att-admin-key (data/prr-admin.key), base64, 0600,
made on first start.
Asset gate (v5.62, issue #248 option B): devel's Caddy asks CC before it
passes /rr3/live/* and /assetman/* to the asset server (forward_auth to
GET /prr-gate/asset, which only a peer on this machine may call; Caddy
copies the phone's headers and adds X-Forwarded-Method/-Uri). CC checks
the phone's X-PRR-Att token like /prr/api/att/check (attested, not
blocked, build allowed; each verdict cached 60 s per token and IP) and
logs it with the full User-Agent. Log only (always 204) unless
--asset-gate-enforce: then 403 {"ok": false, "reason"}. CC's own update
set (asset_list_updates) gets the same check and mode.
--attest-state keeps the results (data/rr3-attest.json, private),
--attest-status Google's revocation list (data/attest-status.json,
refreshed daily).

Secret reset (v5.25, issue #163): a reinstalled phone makes a new secret,
which the server ignores while it keeps the old one, so login fails. The
admin adds the member id to --secret-resets (one per line):
    echo 1018 >> data/rr3-secret-resets.txt
The next request (game or website) drops that player's secret, ends their
website sessions, logs "secret reset for member(s) ..." and empties the
file. The phone's next request sends its secret again, and that one is kept.

Race Selector (issue #153): every Debug Race Selector race is event 18130,
whatever the track and car, so the server keeps nothing for it: its
results and ghosts are accepted and dropped, and stored ones are not
shown. Each phone keeps its own bests per track and car
(rr3_selector_times.py).

Online multiplayer schedule (issue #86, step 2): with --omp FILE the
server also answers the OMP schedule (subsync 10536), the only reply the
OMP card needs before matchmaking. FILE is a JSON schedule, see
rr3-omp-schedule.example.json: one car-group key for the event
(data/onlinemp.dat; since v5.15: the reply's three car lists are one per
league and the game only uses league 1), three races, each a track id
(Tracks/ttk.dat), and the event length in seconds (since v5.4 one
window for every phone: events start at multiples of the length in Unix
time, e.g. every Thursday 00:00 UTC for 7 days, and each reply sends the
seconds left in it; the game rotates the three races by server time, so
all phones and StartMatch see the same race). Since v5.18 the file may
hold a list of `events` (each its own cars, races, rewards, period, week):
window n of `seconds` answers event n % count, so the car class changes by
itself; the week id is the window number unless the event sets one.
--omp-data takes the phone's onlinemp.dat (decrypted with rr3_nct.py) to
check the car-group keys at start-up; --omp-groups FILE prints its groups
with car names and exits. Since v5.2 it also answers StartMatch (10626),
sent when the game server (rr3_mp_server.py) starts a race: a match id,
the schedule's current race (track and laps, chosen as the game rotates
them: race (1 + server time / period) % 3, period 300 s unless the
schedule sets `period`, v5.15) and the week id the phone sent.
The game only goes on with at least one other player in the room
(analysis/online-multiplayer.md, "Q9: StartMatch 10626"). Since v5.19 it
answers FinishedMatch (10532), sent at race end: the match's id, track
and laps (kept from its StartMatch), the request's field 3 and week, and
since v5.20 one result row per player; since v5.67 (#521) the row is
(player value, place, status, time ms, rating before, rating after), with
ratings 1000 / 1000 (change 0). A request row is (player value, the
status that phone gives the player: 1 finished, 2 left, 3 disconnected,
0 nothing yet; the race time in ms, 0xFFFFFFFF = none yet; a flag,
[slot+0x7e]): v5.43-v5.66 read the status as a position, v5.20-v5.42
the time as the status. --omp-rating-test (v5.43) sends made-up rating
before / after values to see where the results screen shows them. Before v5.19, unanswered, the phone stayed
in OMP state 5 ("syncing results") and its matchmaking screen never
matchmade again until OMP was entered from the main menu; with v5.19's
reply but no rows it stayed on "server verifying results" (issue #233).

Files, by default next to this script:
  server.key                 --server-key
  data/rr3-leaderboard.json  --times
  data/rr3-usernames.json    --usernames
  data/rr3-username-claims.json --username-claims (v5.74)
  data/rr3-members.json      --members
  data/ghosts/               --ghosts (ghost files and index.json)
  data/saves/                --cloud-save-dir (cloud save backups by member id, v5.63; private)
  data/rr3-mail.json         --mail
  data/rr3-secrets.json      --secrets (private: mode 0600)
  data/rr3-friends.json      --friends
  data/rr3-friend-details.json --friend-details (friends' stats and cars, v5.53)
  data/rr3-secret-resets.txt --secret-resets (admin: member ids to reset)
  data/rr3-secret-reset-requests.json --secret-reset-requests (private, v5.54)
  data/blocklist.txt         --blocklist (admin: players and IPs refused)
  data/rr3-omp-matches.json  --omp-matches (open OMP matches, v5.47)
  data/rr3-omp-results.jsonl --omp-results (settled OMP races, v5.47)
  data/public-hidden.txt     --public-hidden (admin: hidden from public pages)
  data/lb-banned.txt         --lb-banned (admin: leaderboard ban, v5.80)
  data/rr3-omp-leagues.json  --omp-leagues (OMP league picks and the league served, v5.48)
  data/rr3-omp-ratings.json  --ratings-file (OMP ratings, written in on, v5.79)
  data/rr3-omp-ratings-shadow.json(l) --ratings-shadow-file (shadow ratings + room log, v5.79)
  logs/                      --out (with --save)

Limits for a server other phones reach (issue #143, analysis/server-safety.md):
bodies over 1 MB (syncs: 8 MB, v5.40) get 413, a bad Content-Length or chunk size 400, a
connection idle for 30 s is closed; a sync body must be wrapped as the
game does (one XOR layer around zlib or plain, unpacked at most 4 MB) or
it is only recorded; a Time Trial result with a negative car id or a PR
that is not a number from 0 to 1000 is not stored. Since v5.45 (item 5)
its car must also be in the game's car list (--cars, default
data/car-index.csv, a copy of the repo's tables/car-index.csv; a missing
file checks only car >= 0 and says so at start; --no-cars) and its time
from 1 ms to 30 min, when it is stored and when rows are served; a ghost
with a car not in the list is dropped; stored times that fail are moved
to <times>.rejected.json at start (the file is copied to
<times>.bak-v5.45 first). Since v5.10 at most
--max-connections (default 64; 256 since v5.83) connections are handled at once (more are
closed at once; since v5.81 connections from this machine, i.e. Caddy,
have their own --local-connections slots, default 64) and a request must arrive complete within 60 s, so slow
clients cannot hold the server's threads (8.5). Since v5.83 (#248) an idle
connection waits at most --keepalive-s (default 2) for its next request,
the listen queue is --listen-queue (default 512), --per-ip N caps one IP's
phone connections (default off), slow requests get a "slow:" line and a
"slots:" line is logged once a minute. Since v5.12 (item 6) one
IP adds at most --new-players-per-ip (default 10) new players an hour
(more get --status, unanswered), a player holds at most 2 open ghost
upload keys and all players 256 (the oldest are dropped), a leaderboard
sends the 100 fastest rows plus the asking player's own, and with
--events FILE (the repo's tables/event-index.csv) results and ghosts are
kept only for the game's real events.

APK signature label (v5.11, issue #143, docs/apk-signature-label.md; not
tested in game): an APK with the smali change sends "sig:" + the SHA-256 of
its signing certificate in the request header. With --answer every
request's log line says "apk <name>" for a trusted digest (v5.29: the
key's name from --trusted-sigs FILE, e.g. "apk devel", "apk tom"; a digest
given with --trusted-sig is "apk trusted"),
"apk other" (another digest, shown shortened, or "sig:none") or "apk
unknown" (no "sig:" string: every APK without the change). Log only:
nothing is refused or filtered by it. The digest is public, so the label
stops casual re-signed copies, not someone faking it (proof: issue #204).
With --shadow-other (v5.13, needs --trusted-sig) a player whose latest
request is "apk other" is shadowed: they sync and race as before and see
their own times, ghosts and mail, but nobody else is shown their
leaderboard rows (10477, 10516), sent their ghosts (10476) or mailed about
their times (10459), and they don't count in the player total. A request
labelled devel or unknown makes them visible again. Kept per player key
in --shadowed (log: "apk other (..) (shadowed)").

Asset updates (v5.31, issue #292; not tested in game): with --asset-update
DIR, every file under DIR is offered to the phones as a game file with the
same path (DIR/data/events.dat.nct -> /data/events.dat.nct). The server
answers the update check 10449 with the list name asset_list_updates.txt
and the list's md5; a phone whose list differs downloads it from its CDN
host, which must send /rr3/live/asset_list_updates* here (devel's Caddy
route). Served: <list md5>.txt (the list), <list md5>.bin (the pack: per
file u32 djb2(path) % 0x106d643d, u32 length, FMASZ1 + zlib body) and
<file md5>.txt (one file), each with the 8-byte header the game checks
(the list's name is hashed without a leading /), with Range. Files are read again when
they change. An empty or missing DIR answers nothing (as before v5.31).

Tester asset set (v5.35, issue #311): --asset-test DIR is a second set
built the same way, offered only to the member ids in --asset-testers FILE
(one per line, # comments; read again when it changes). A listed member's
10449 gets the test list (log: "asset update test <md5>"), everyone else
gets --asset-update's (or nothing). The test DIR replaces the normal set
for testers, so it must hold every file they should have. Both sets are
served under /rr3/live/asset_list_updates/.

No asset update for iPhones (v5.66): an iPhone's 10449 (a sync with an
IDFV or a PRR iNN build label) is not answered (log "no asset update
(ios)") unless CC runs with --asset-update-ios. iPhones therefore never
get our PRR_ OMP groups: an OMP event using one needs `ios_cars` or
`ios_leagues`, the group(s) an iPhone's 10536 gets instead.

Only the Python standard library is used. Stop with Ctrl+C.

Usage:
  python rr3_cc_server.py [--port 8080] [--bind 127.0.0.1] [--out DIR] [--status 503] [--save]
                          [--answer [--name NAME] [--names FILE] [--tag PRR] [--times FILE]
                                    [--usernames FILE] [--members FILE] [--server-key FILE]
                                    [--skip-queued] [--ghosts DIR] [--ghost-url URL] [--mail FILE]
                                    [--cloud-save [--cloud-save-dir DIR] [--cloud-save-max-bytes N]
                                                  [--cloud-save-versions N]]
                                    [--omp FILE [--omp-data onlinemp.dat]]
                                    [--trusted-sigs FILE] [--trusted-sig SHA256 ...]
                                    [--build-allowlist FILE]
                                    [--events event-index.csv] [--cars car-index.csv | --no-cars] [--new-players-per-ip 10]
                                    [--shadow-other [--shadowed FILE]]
                                    [--secrets FILE] [--friends FILE] [--friend-details FILE]
                                    [--secret-resets FILE] [--secret-reset-requests FILE]
                                    [--asset-update DIR]
                                    [--asset-test DIR --asset-testers FILE]]
  python rr3_cc_server.py --omp-groups onlinemp.dat
"""
# Server version (shown at start-up). Bump it with every change to what the
# server answers; v5.0 adds the online multiplayer schedule (--omp); v5.1
# adds the limits of issue #143 and saves requests only with --save; v5.2
# answers StartMatch (10626) with --omp; v5.3 logs the race rotation
# (server time, second of the 5-minute slot, race) with 10536 and 10626;
# v5.4 gives every phone the same event window (aligned to its length);
# v5.5 drops Race Selector results and ghosts (event 18130, issue #153);
# v5.6 answers 10516 (Ghost Challenge rows) and 10459 (mail "someone beat
# your time"); v5.7 answers 10419 (friends' results per event, no rows);
# v5.8 accepts usernames with ! ? ~ + * # (rr3_username.py v3 rules);
# v5.9 mails at most 20 passed players per new best and saves the mail
# file once per request (issue #143, analysis/server-safety.md 8.1); v5.10
# handles at most --max-connections connections at once and closes a
# request not complete within 60 s (issue #143, 8.5); v5.11 labels each
# request with the APK's signature (--trusted-sig; log only, issue #143);
# v5.12 caps what fake players can fill (issue #143 item 6): new players
# per IP, open ghost upload slots, leaderboard rows sent, known events only
# with --events; v5.13 can shadow players on APKs not signed by a
# --trusted-sig key (--shadow-other: their times, ghosts and mail are
# hidden from everyone else; issue #143); v5.14 answers GET /time with
# the server time in the X-Request-Start header (issue #197, for a lib made
# with rr3_cc_local.py sync v2); v5.15 sends one car group for the whole
# OMP event (schedule `cars`, in all three car-list fields: they are per
# league and the game only uses league 1) and the optional rotation
# `period` (10536 field 19; also used for the StartMatch race); v5.16
# keeps each player's secret from the header (rrsecret:), serves the friends
# site's login and API under /prr/ and answers 10419 with friends' rows and
# 10556 (issue #218); v5.17 counts a right login code sent again (a second
# tap in the same minute) as no failed try, and sends a player who is still
# logged in to /prr/ instead of the failed page (issue #220); v5.18 takes
# a list of OMP `events` and answers the one of the current window, so the
# car class changes by itself (issue #227, option C); v5.19 answers
# FinishedMatch (10532), so players can matchmake again after a race
# (issue #233); v5.20 adds a result row per player to that reply (without
# rows the phone stayed on "server verifying results", issue #233); v5.21
# optionally enforces an exact PRR build allowlist before Cloudcell side effects;
# v5.22 reuses a recently verified build for same-player syncs without type 68;
# v5.23 can write the IPs of allowed syncs to a shared admit file
# (--build-admit-file) for servers that see no build label, such as asset
# downloads (issue #242, rr3_build_policy v1.1); v5.24 answers subsync 68
# (StatManager game sessions) with status 1, so the game drops the sessions
# it already sent and the build label in 68 is the newest session's
# (issue #242, analysis/stat-manager-sync.md); v5.25 reads an admin
# reset file (--secret-resets, one member id per line): the next request
# drops those players' secrets and ends their website sessions, so a
# reinstalled phone's new secret is kept (issue #163); v5.26 answers the
# friends leaderboard tab (10486) with the player's and their PRR friends'
# times on the event (issue #163, analysis/social-login.md section 5.2);
# v5.27 leaves the asking player out of 10486: the game adds its own row,
# so the player was shown twice (b48 test, 2026-11-02); v5.28 takes the
# build tag from the User-Agent first (built fresh by the running lib on
# every request), then subsync 68, then the same-player cache; when the
# User-Agent and 68 disagree the User-Agent wins (issue #272); v5.29
# reads the trusted APK signing keys with a name each from --trusted-sigs
# FILE (re-read when it changes) and logs that name ("apk tom") instead of
# "apk devel" for every trusted key; --trusted-sig keys log "apk trusted";
# v5.30 drops the fake rivals: an event with no stored time gets no rows
# (--rivals is accepted and ignored), and every 10477 and 10484 of a
# request is answered for its own event; 10484 sends one band, ALL at
# TOP 100% with the event's entry count + 1 as rank cutoff (issue #200);
# v5.31 --asset-update DIR answers the asset update check (10449) with
# asset_list_updates.txt and serves that list and its pack under
# /rr3/live/asset_list_updates/, so a changed game file (first:
# data/events.dat.nct with our WTT dates) reaches every phone without a
# build (issue #292, analysis/asset-download.md section 4.1); v5.32 sends
# the same 8-byte header (hash, length) before a single .txt file too: the
# game refused v5.31's bare list with "Didn't match its hash" (Tom's test,
# 2026-11-03); the list's name is hashed as asset_list_updates.txt;
# v5.33 accepts iOS build labels `PRR iNN-channel` too (rr3_build_policy
# v1.2, rr3_cc_blob; issue #299); v5.34 logs the shapes of the header's
# strings (uuid, 16hex, digitsN, ...; never their values) when a request
# has no Android id and no Synergy id, so its player key is "unknown", to
# see what an iPhone sends (issue #299); v5.35 adds a tester asset set:
# --asset-test DIR for the member ids in --asset-testers FILE only, so the
# LTS / Seasons / Featured quest files reach testers first (issue #311);
# v5.36 answers POST /time like GET: the game sends POST, so every server
# time request failed with --status (Tom's logcat, 2026-11-04, #325);
# v5.37 refuses blocked players and addresses with 403 (--blocklist,
# data/blocklist.txt, rr3_build_policy v1.3, issue #332); v5.38 checks
# Android key attestation (GET /prr/attest/challenge, POST /prr/attest,
# rr3_attest.py; needs the cryptography package) and adds "att ..." to each
# sync's log line, log only (issue #204).
# v5.39 --prize-test MEMBER:EVENT[,EVENT...] (MEMBER "all" = every member)
# answers subsync 10781 (the competition prize-winner list: u32 count, u32
# event ids) for that member, to test whether the game pays WTT/TTC gold (issue #193,
# analysis/weekly-time-trial.md section 10); without it 10781 stays
# unanswered as before;
# v5.40 accepts sync bodies (POST /CC_Sync.php) up to 8 MB (iOS sends
# larger ones; ghost uploads keep 1 MB) and logs the declared length and
# User-Agent of a refused body (issue #299);
# v5.41 logs, for a sync the build gate denies, its User-Agent, its subsync
# types, the printable start of its subsync 68 report and its id shapes
# (never the id values), to see where an iPhone puts its build tag (#299).
# v5.42 validates ghost files (issue #357, analysis/ghost-files.md 4): on
# PUT (400 if bad), at 10694 (record must match the link, else dropped) and
# stored ones at start (bad ones move to rejected/); ghost PUTs up to 64 KB.
# v5.43 reads a FinishedMatch row as (value, phone position, time ms, flag)
# (v5.20-v5.42 took the position for the time and the time for the status;
# analysis/online-multiplayer.md "FinishedMatch fields read from the live
# CC log"), ranks by it, logs the sender's slot, the phone position, time
# and flag per player, and StartMatch's player values; --omp-rating-test
# sends +17/1234, -9/987 in the rating columns (issue #262).
# v5.44 sends Content-Security-Policy: frame-ancestors 'none' and
# X-Frame-Options: DENY on every response under /prr/ (login, API, attest,
# errors), so no other site can frame the friends site (issue #359).
# v5.45 checks the client values other phones see (issue #143 item 5):
# car ids against the game's car list (--cars, default data/car-index.csv,
# the repo's tables/car-index.csv; missing file = car >= 0 only, with a
# warning; --no-cars), Time Trial times 0 < t <= 30 min, PR as v5.1; when
# storing a result (10451), serving rows (10477, 10516, 10419, 10486) and
# mailing; a ghost with an unknown car is dropped at 10694 and at start;
# stored times that fail move to <times>.rejected.json at start (original
# copied to <times>.bak-v5.45 first).
# v5.46 keys an iPhone by its identifierForVendor (header typed entry 1,
# read by rr3_cc_blob.header() since this change; an iPhone has no Android
# or Synergy id), so it gets its own member id and its syncs without a 68
# pass as "(cached)" (#299). A re-sign with another Apple ID changes the
# IDFV: a new player. First deployed as a branch-only "v5.42" on
# 2026-11-05 ~16:22 (not main's v5.42), dropped by the v5.43 deploy.
# v5.47 keeps OMP matches and their results (issue #360, spec #359): open
# matches in --omp-matches (reloaded at start; replaces the memory-only
# OMP_MATCHES), settled when every starter has reported or 2 min after the
# first report (cap 10 min after the start), one record per race appended
# to --omp-results (`ranked` false, ratings null); FinishedMatch replies
# unchanged. Public read-only GETs /prr/api/matches, match/<id>,
# player/<pid>/matches, players?q= (no cookie; date only, no member ids;
# max-age=30, X-Robots-Tag noindex; 120 a minute per IP); me/matches with
# the cookie; --public-hidden shows listed members as "Player" (R6).
# v5.48 OMP leagues (issue #264): a schedule event may set `leagues` (one
# car group per league) and `league_rewards`; 10536 sends the asking
# member's league's group (fields 4-6) and reward (field 7). League 2
# unlocks at 10 finished races, league 3 at 20 (races_finished, #360), for
# good; a member races in their pick (GET/POST /prr/api/me/league, cookie)
# if unlocked, else their highest. The league served is kept in
# --omp-leagues (data/rr3-omp-leagues.json), which rr3_mp_server.py v0.23
# reads to split rooms; settled records carry it as `league`.
# v5.49 settles finished players by the position their phones gave them,
# then time (v5.47-v5.48 by time only: a player who quits reports last but
# with a shorter time than the winner, so he was ranked first; Tom's races
# of 2026-11-03, analysis/online-multiplayer.md "FinishedMatch fields read
# from the live CC log"; the FinishedMatch reply has done this since v5.43).
# v5.50 (#383, #264 tests): an admin "force": 1-3 in a member's entry of
# --omp-leagues puts them in that league whatever their unlocks (for
# testing leagues 2/3 and our own car groups); the file is read again when
# it changes on disk, so the entry needs no restart. The API never sets it.
# v5.51 (#264, #259): the flag does not mark a quit (Tom, 2026-11-06: a
# hand quitter reports flag 0, last, with the time he quit; the game ends
# the remaining player's race). At settle, a finished player whose time is
# shorter than that of a player the phones placed ahead of him is "left"
# (no time); races_finished counts a room only if at least 2 players
# finished it (was: 2 starters), so a quit race unlocks nothing.
# v5.52 answers 10785 (SyncPendingMatches) with every match id the phone
# lists, so the phone drops them all: it keeps a match id from its start
# until it processes the FinishedMatch result, and one that never got there
# (a quit) stayed for good and is the likely cause of the OMP card's
# RATING PENDING (analysis/online-multiplayer.md "MemberStatus 10548 and
# pending matches 10785", PR #388). The server owns the results, so the
# phone's list has no use with our servers. 10548 stays unanswered (its
# reply changes nothing).
# v5.53 answers 10472, the friends' details (issue #278,
# analysis/social-login.md 9.2), which fill the game's friends screens and
# "N friends own this car"; rr3_prr_social.py v2 makes the phone send it.
# Each player's own 27 stats and owned cars from their 10472 are kept in
# --friend-details (data/rr3-friend-details.json; car ids not in --cars
# dropped, sizes capped, a request not read to its exact end is not
# stored) and sent to their PRR friends: name, member id, "prr:<member>",
# seconds since their last 10472, stats, cars. A friend with no stored
# values (or shadowed) is sent without stats or cars.
# v5.54 (#278): the 10472 request carries 26 stats, not 27 (Tom's b52
# capture; v5.53 refused every real request with "list of 0 bytes"). The
# reply's 27 are request words 1-24, the friend's number of friends
# (FriendDetails +0xec), then words 25-26 (analysis/social-login.md 9.9).
# Stored entries with 27 stats (none were ever written) are dropped.
# v5.54 (#423 parts 1 and 3): a phone that sends a secret other than the
# kept one is logged once per run ("secret differs from the kept one");
# that newest secret is remembered in memory. A wrong login code that
# matches it logs "wrong code (phone's secret changed ...)", redirects to
# /prr/?login=failed&reason=secret-changed and files a reset request in
# --secret-reset-requests (data/rr3-secret-reset-requests.json, private;
# one per member, a later one replaces it). An admin approves with the
# usual --secret-resets line: with a request open, the requested secret is
# kept at once (no race for "the next secret"); without one, as before.
# v5.55 (#427 R1, test only): --news-test FILE answers the news room sync
# 10748 for the members listed in the JSON file with its categories and
# items (analysis/online-multiplayer.md "News items can open the invite
# popup"), to find where a news item shows and what its deep link does.
# The file is read again at every 10748, so a test can be changed without a
# restart; other members, or no option, get no answer (as before).
# v5.56 (#427 phase 2, OMP invites): the host's 10455 (SyncUserPNE: invitee
# member id, notice template, rr3://MultiplayerInvite link) is kept in
# --omp-invites (data/rr3-omp-invites.json, private: it holds the pass key;
# rr3_mp_server.py v0.24 --invites reads it) when the room is in MP's
# --omp-private-rooms file with this host and the two are PRR friends;
# invites last 15 min. The invitee's 10748 gets a one-time news popup per
# invite ("X invited you to race"; analysis/online-multiplayer.md "News
# test results"); GET /prr/api/me/invites lists them with the rr3:// link
# and an intent:// link (deepLinkUrl + alert) for the site's Join button.
# An OMP match whose players are one invite group is kept with "private":
# true and does not count for league unlocks (Tom, 2026-11-07: unranked).
# v5.57 (#452, Tom 2026-11-08: enforce attestation): --attest-enforce refuses
# a CC_Sync request (403, after the blocklist and the build allowlist) from a
# player whose latest proof did not pass within 24 h. Its rrsecret is kept in
# memory (pending, at most PENDING_SECRETS_MAX, never written) when the player
# has no kept secret, and /prr/attest checks against it; the first answered
# sync keeps it as before. /prr/attest answers 503 when there is no secret at
# all, so PrrAttest v1 tries again (it does so on any status >= 400). The
# --build-admit-file gets only IPs of syncs that pass both checks.
# --attest-enforce without working attestation stops CC at start.
# v5.58 (#452 phase 3): a passing proof's /prr/attest answer carries a token
# ("v1.<payload>.<mac>", rr3_attest.make_token: member, 16 hex of the player
# key, the build of the player's latest sync, level, signer, expiry = proof
# + 24 h) signed with --att-token-key (data/prr-att.key, base64, 0600, made
# on first start). POST /prr/api/att/check {"token", "sig", "ip"} with
# X-PRR-Admin (--att-admin-key, data/prr-admin.key) answers 200 {"ok",
# "member", "build", "level", "signer", "exp"} or 403 {"ok": false,
# "reason"}: bad token, expired, not attested (latest proof failed or too
# old), blocked (member or ip), build not allowed. For devel's asset
# server (#248). Requests under /prr/ are never saved with --save.
# v5.59 (#451, Tom 2026-11-08: let iPhones in while attestation is
# enforced): --attest-ios-exempt. With --attest-enforce, a sync that would be
# refused for "att none" is answered when it comes from an iPhone: the header
# carries an IDFV and no Android or Synergy id (so the player key is the IDFV
# one, v5.46), a player secret (rrsecret:, rr3_ios_prr_secret.py), and the
# build gate passed it as an iOS label (PRR iNN-channel). The log says
# "att none (ios exempt)". An iPhone can't attest yet (no App Attest without a
# paid team, #451), so this trusts the IDFV and the secret only: anyone can
# send an IDFV, so it reopens enforcement to anyone who fakes an iPhone
# header with an allowed iOS label. Without a build gate nothing is exempt.
# Exempt iPhones get no attestation token.
# v5.60 (#469 part 3, Race Selector P2P): --omp-selector-rooms (MP v0.26's
# --selector-rooms, data/rr3-omp-selector-rooms.json, read when it changes)
# lists locked selector rooms (members, track, laps). A StartMatch whose
# members are such a room (locked at most SELECTOR_ROOM_S ago; exact member
# set first, else the newest room holding them all) gets the room's track
# and laps; the match is kept with "selector": true, counts for no league
# unlock (Tom, 2026-11-08: unranked), and the site's head says so.
# v5.61 (#451, bug from the box 2026-11-09: an i06-alpha iPhone was still
# refused, "att none denied build PRR i06-alpha (68)"): --attest-ios-exempt no
# longer requires "no Android or Synergy id". An iPhone's typed entries 5/6
# are Cloudcell's stored strings (on Android one is the Synergy id) and
# entry 4 is a cached string, so a real iPhone can carry an all-digit or
# 16-hex string that blob.header() reads as a Synergy or Android id. The
# exemption now needs an IDFV (type-1 entry, which Android never sends), a
# player secret and an allowed iOS label; the player key is unchanged. A
# refused sync with an iOS label (flag on) logs why it wasn't exempt and the
# header's id shapes (no values): "(ios: no secret; ids …)".
# v5.62 (#248 option B, Tom 2026-11-09: CC decides asset downloads): GET
# /prr-gate/asset for Caddy's forward_auth in front of devel's asset server
# (/rr3/live/*, /assetman/*). Only a peer on this machine; the path is under
# no public Caddy route. It reads the phone's headers as Caddy copies them
# (X-PRR-Att, X-PRR-Sig, User-Agent, CF-Connecting-IP, X-Forwarded-Method,
# X-Forwarded-Uri), checks the token as /prr/api/att/check does (shared
# token_verdict()), caches each verdict ASSET_GATE_CACHE_S per token and IP
# (a pack is many Range requests) and logs every request with the full
# User-Agent ("asset gate ... ua '...': ok|reason (log only) -> 204"). Log
# only: always 204. --asset-gate-enforce: 403 {"ok": false, "reason"} (needs
# attestation; CC won't start without it). A 204 carries X-PRR-Member. The
# request body is never read (forward_auth may pass a POST's length on) and
# the connection is closed. The asset_list_updates GET (CC's own set) gets
# the same check and mode. Enforcing waits for attest-dex@v2 builds and for
# Tom's choice for iPhones (#248 open question 3).
# v5.63 (#501 phase (a), Tom 2026-11-09: cloud save backups only; analysis/
# cloud-save.md): with --cloud-save, 10660 (upload slot) gets status 1, a
# one-use key (1 h, at most 2 open per member) and <--ghost-url or
# http://Host>/save/<key>; PUT /save/<key> (own limit --cloud-save-max-bytes,
# 9 MB) keeps the body as received in --cloud-save-dir/<member>/<UTC>-<md5>.bin
# (temp file, fsync, rename; same md5 as the newest: not stored, still 200;
# the oldest beyond --cloud-save-versions, 3, goes only after the new one is
# in place); 10661 (done) gets u32 1; a corrupt-save report 22 keeps its
# inline save under <member>/corrupt/ (3 kept, apart) and gets an empty
# answer. Logs member, size, md5, stored / same as newest and the count,
# never content; a sync refused for its unpacked size names the subsyncs
# seen. 47 / 48 stay unanswered; 10555 is never answered (0 deletes the
# player's progress). Without --cloud-save nothing changes.
# v5.64 (#501, Tom's A32 test 2026-11-09: slot answered, no PUT, "Cloud save
# failed"; analysis/cloud-save.md 2.2, 2.3): the 10660 reply reader
# (0x1ce8d88) goes on only on status 0 (cbz at 0x1ce8de4), the opposite of the
# ghost slot 10695, so 10660 now gets u32 0, then the key and URL as before.
# With --cloud-save, a list request 47 from a player with a key and member id
# gets a valid empty list, u32 0, 0, 0 (B != 1: ok, no saves; 0x1cea6a4);
# real saves are never listed in phase (a). 10661 still gets u32 1; 48 stays
# unanswered; 10555 is never answered. Without --cloud-save nothing changes.
# v5.65 (#514, cloud save phase (b), Tom 2026-11-09; analysis/cloud-save.md
# 2.3): --cloud-save-restore FILE (member ids; needs --cloud-save). A listed
# member's 47 gets one row (the game shows only one): A 0, B 1, N 1, one
# entry for the newest stored version (id = first 8 hex of its md5, time =
# its upload time, empty meta: "Last Uploaded", no progress, no auto prompt)
# and a one-use GET URL <--ghost-url or http://Host>/save/<key> in the tail
# (1 h, 2 per member, 64 in all, in slots.json "restores"). GET /save/<key>
# sends the stored bytes unchanged (403: blocklist, build no longer allowed;
# 404: unknown or used key, file gone); once sent in full the version is
# pinned (pins.json): never rotated out and not counted in
# --cloud-save-versions; the next restore moves the pin. 48 and 10555 are
# still never answered; members not listed, and every member without
# --cloud-save-restore, get the v5.64 empty list.
# v5.66 (Tom 2026-11-09: "disable updates on iOS builds"): an iPhone's asset
# update check (10449) is no longer answered, so iPhones are never offered
# our update list (assets/: data files, music, logo, onlinemp.dat.nct). An
# iPhone is a sync with an IDFV (header type-1 entry) or an iOS build label
# (PRR iNN-channel); log "no asset update (ios)". --asset-update-ios offers
# it to iPhones again (as v5.65). iPhones had never fetched the list
# (cc.log 2026-11-09: 182 offers, 0 asset_list_updates GETs, #401). Since
# they never get our groups file, the OMP schedule takes `ios_cars` (one
# group) or `ios_leagues` (3 groups) per event or file-wide: an iPhone's
# 10536 gets that group instead of the event's (log "ios"). An event whose
# group (cars or a league) starts with PRR_ needs one, and an iOS group
# can't be a PRR_ one: a phone without the group crashes on the OMP card
# (#383 test 3). Whether an iPhone and an Android phone on different groups
# can share a match is untested. EA's game packs are not affected.
# v5.67 (#521, Tom 2026-11-09: the OMP results screen showed 00:00:00.001,
# .002, .003; analysis/online-multiplayer.md "FinishedMatch reply rows",
# PR #527): a FinishedMatch reply row is now key, place, status, time ms,
# rating before, rating after (v5.20-v5.66 sent key, place, time, the
# request's 2nd field, 0, 1000: the screen showed that 1/2/3 as the time
# and +1000 as the change). The request's 2nd field is the phone's
# **status** (1 finished, 2 left, 3 disconnected, 0 none yet), not a
# position (v5.43-v5.66's reading). Place: finishers (status 1, time known)
# by time, then the rest; 1..n, never 0. Status / time per player: their
# own report (this one or one kept in the open match), else the best other
# report; status 1 with a bad time (#143) is sent as DNF (0xFFFFFFFE).
# Ratings 1000 / 1000 (change 0) until #263; --omp-rating-test sends made-up
# before / after. Settle: status 2 = left, 3 = dnf (disconnected), 0 = dnf;
# v5.51's time check stays only as a fallback for a status code not in
# OMP_STATUS (4 and up): left if a status-1 finisher has a longer time.
# Finishers are ranked by time. The log shows "status" for "phone".
# v5.68 (#522, Tom 2026-11-09: live OMP status on the site): public GET
# /prr/api/live = {"online", "racing", "rooms", "window_s"}. Online = players
# whose game request CC answered in the last LIVE_ONLINE_S (300 s), keyed by
# member id (else the phone's player key; memory only, a restart starts at
# 0; site API calls don't count). Racing / rooms = open matches with a
# StartMatch (league, track, laps, players, whole minutes since the start);
# invite and Race Selector rooms only "private", players and minutes. No
# names, member ids, pids or timestamps. max-age=15, the same rate limit.
# The log says "live: online N, racing M, rooms K" once a minute.
# v5.69 (#522, Tom 2026-11-09: "count any request with a known player, not
# just syncs"): "online" also counts a phone's attestation, cloud save
# (GET / PUT /save/), ghost upload, asset download and asset gate requests,
# and an ok token check (/prr/api/att/check), by the member id they name. A
# request refused (blocklist, build, attestation, asset gate enforced) or
# without a member (/time) is still not counted.
# v5.70 (#514, Tom 2026-11-09: "We would want this to be extremely safe"):
# before a stored cloud save version is offered (47) or sent (GET
# /save/<key>), save_check() checks (1) its md5 against its name, (2) the
# BinaryBlob mode 1 checksum, (3) that zlib unpacks it completely to the
# declared size, and (4) the bundle: u32 2, u32 3, exactly character.2.dat,
# player_profile.2.dat and nrc.bin.2.dat, with character.2.dat's magic,
# version 5, size field and checksum byte right (analysis/cloud-save.md 2.6).
# A failing version is never offered or sent (GET: 404, no pin), the next
# newest that passes is offered, none passing = the empty list; the file is
# left in place and logged ("save check failed: member M: <file>: <why>").
# 47 results are remembered by size and mtime.
# v5.71 (#542 online dashboard, #374 public online numbers; Tom 2026-11-09):
# /prr/api/live also lists the rooms waiting in MP's lobby ("lobby", from
# rr3_mp_server.py v0.28's --status-file, read via --mp-status; ignored when
# missing or older than MP_STATUS_STALE_S), every room gets "state" and
# "max", public rooms get "names" (hidden or shadowed = "Player N", no
# member = "Guest"; private rooms never), plus "rooms_open" and "in_lobby".
# A lobby room whose players are already in a racing room is shown once,
# as racing. New public /prr/api/top = Top 10 wins / podiums / races
# finished, all-time, public rooms with 2+ finishers only, ties to whoever
# got there first, hidden players "Player N" keeping their rank; counted
# as records are indexed (load and settle), sorted once per change,
# max-age=60. New public /prr/api/status (#374) = online_5m, online_1h,
# players_today (UTC day), races_today and MP's rooms / in_rooms /
# searching (null when MP's file is missing or stale), since, updated
# (minutes). No member ids, pids, IPs or times finer than a minute in any
# of them. "online" keeps v5.69's meaning.
# v5.72 (#530, Tom 2026-11-09): preset saves from the site. --cloud-save-
# presets FILE (JSON: id, name, file = a character.2.dat used as-is) lists
# them; GET /prr/api/me/cloudsave (login) shows them with the member's
# stored versions; POST me/cloudsave/preset {"id"} stores the preset with the
# member's own player_profile/nrc from their newest good upload as their
# newest version (save_check first; twice per 24 h) and opts them in to
# restores (site.json, apart from --cloud-save-restore); their last own
# upload before a preset becomes the base, kept like a pin until POST
# me/cloudsave/own makes it the newest again; me/cloudsave/optout ends the
# site restores. The page's calls run outside the server lock.
# v5.73 (#530, Tom 2026-11-09: "give restores to every member"; "Android only
# for now"): --cloud-save-restore-all gives every member the 47 row for their
# own newest good version (the v5.70 checks still apply), except when the
# sync carries an iOS build label (IOS_BUILD_RE); the tester file and site
# opt-ins still work for anyone, iPhones included. Off without the flag.
# v5.74 (#178, Tom 2026-11-09): one in-game username per player. The first
# member to send a name holds it (--username-claims, by member id, so a
# member move keeps it); case doesn't count ("Tom" = "tom"), and --names
# values are reserved for their own player. Anyone else sending a held
# name is shown as "Name (2)", "(3)", ... (no player can type a space, so
# never a real name); --usernames keeps the name shown, so MP's roster and
# member moves see the same. A rename or a cleared name frees the old one
# at once; the next player sending it gets it from their next request.
# Built once from --usernames when the claims file is missing: the lowest
# member id keeps a duplicated name. GET /prr/api/me adds "name_taken" (the
# name the player chose) while they are shown with a suffix.
# v5.75 (#574, Tom 2026-11-09: every rotation on Tuesday 00:00 UTC): the OMP
# schedule's `offset` (seconds, 0 to seconds - 1, default 0) moves the event
# windows: window n = (now - offset) // seconds. 432000 (5 days) starts
# 7-day weeks on Tuesday 00:00 UTC instead of Thursday; with it, Tuesday
# window n starts two days before Thursday window n, so switching between
# Tuesday and Thursday 00:00 keeps the current window's number and event.
# v5.76 (#193, WTT gold): --prize-events FILE (the WTT prize table from
# rr3_wtt_dates.py prizes: event id, start, end) answers 10781, the prize
# list, for each member: the WTTs that ended by our schedule within the last
# --prize-days (14), that the player has a stored time in, and that this
# member was not sent before (the record --prize-sent, next to --times).
# 10484 for a competition (first payload word 5) sends the 8 bands of
# ttc_rewards_primary_640 (TOP 0.1% ... TOP 100%) with rank cutoffs from
# the event's entry count and the lap time at each cutoff; a normal Time
# Trial keeps the one ALL band. --prize-test still overrides for a member.
# v5.77 (Tom 2026-11-09: "a counter with the members registered in the
# site"): /prr/api/status adds "registered", the number of member ids CC has
# given out (every player that ever got one, hidden players included). A
# number only: no ids or names.
# v5.78 (#86, Tom 2026-11-09: "about 5 min per lap"): the settle cap follows
# the room's laps: laps x 5 min, at least 10 min (as before), at most 60 min
# (settle_cap). A race longer than 10 min no longer loses its late results
# or leaves the Live box before it ends.
# v5.79 (#263, Tom 2026-11-09 decisions 1-6): the OMP rating engine.
# --ratings off|shadow|on, --ratings-start YYYY-MM-DD (shadow turns on at
# 00:00 UTC that day, no restart). A room's ratings are taken when it opens
# (snapshot) and the room is rated at settle, in the mode it opened in:
# one global iRating-style Elo (K 32 / (n - 1), floor 100, start 1000);
# quorum finishers > starters / 2, DNF / left tied last; without a quorum
# only a player who left loses, to every finisher; invite and Race
# Selector rooms unrated. Files: --ratings-file, --ratings-shadow-file
# (+ .jsonl). FinishedMatch sends the stored rating (change 0) once on;
# /prr/api/ratings (public) the table, or {"ranked": false, "starts"}.
# --ratings-report FILE for the shadow week check.
# v5.80 (#607, Tom 2026-11-10: "How do I ban someone from leaderboards?"):
# leaderboard ban by member number. --lb-banned (default
# data/lb-banned.txt), `member N` per line, re-read when it changes (no
# restart). A shadow ban: the member plays and their times and ghosts are
# still stored; they see their own rows; their PRR friends still see them
# in the friends tabs, rival rows, ghost and mail; everyone else gets no
# row (10477, 10484 bands), no ghost, no mail; the site shows "Player"
# with no player page and leaves them out of Top 10 and the ratings
# board; no WTT prize (a WTT due while banned is recorded as withheld and
# never paid). A `member N` in --blocklist hides the same way. Nothing is
# changed in the stores: deleting the line restores everything.
# --lb-banned-report prints what each banned member has stored (read-only).
# v5.81 (#248, Tom 2026-11-10: option C): connections from this machine
# (Caddy: the asset gate's forward_auth, /rr3/live/asset_list_updates*, the
# site) get their own --local-connections slots (default 64), apart from
# the --max-connections slots for phones' direct connections (syncs,
# /prr/attest). On release night forward_auth calls (~175/s) filled all 64
# shared slots and CC refused phones' syncs and attestations. 0 = one
# shared pool, as before v5.81. A refused local connection logs "local slots".
# v5.82 (#360, Tom 2026-11-10: "Finished races counter is broken", "Set the
# settle timer to 5 min"): (1) the settle timer (SETTLE_AFTER_S, now 300 s,
# was 120) starts at the first report with a finished row, not at the first
# report of any kind: a quitter reports at once, and on release night the
# room was settled 2 min later while the others were still racing, so their
# results came in as "late report ... not stored" (match 149698606). The
# cap (settle_cap) still bounds the wait. (2) A finished time below laps x
# MIN_LAP_MS (30 s a lap) is no time (DNF), like one above LAP_CAP_MS (a
# 0:51 for 3 laps of the Nurburgring GP was taken as a win on 11-09); the
# counts apply it to stored records too. (3) Races finished (Top 10 and
# races_finished, so also league unlocks) counts every valid finish of a
# public room with 2+ starters, a solo finisher too (was: rooms with 2+
# finishers); wins and podiums still need 2+ finishers, placed among the
# valid finishers. The site shows "-" as the place of a player who didn't
# finish (tools/prr_site/index.html).
# v5.83 (#248, Tom 2026-11-10): the phone slots were full even at ~14
# requests/s (63 connections, ~50 of them idle; ~1,000 refusals per 10
# min): after an answer a connection waited TIMEOUT_S (30 s) for its next
# request, so idle phones held every slot. Now an idle connection waits
# --keepalive-s (default 2; 0 = close after every answer); the first
# request keeps TIMEOUT_S and REQUEST_S. --listen-queue (default 512) sets
# the listen backlog (was Python's 5: 1.1M kernel listen overflows);
# --max-connections defaults to 256 (was 64); --per-ip N caps one IP's
# phone connections (default 0 = off). Each request is timed (and its wait
# for the server lock); one taking SLOW_MS or more gets a "slow:" line,
# and a "slots:" line once a minute gives busy and peak slots, refusals,
# request count, average and slowest request, the longest lock wait and
# the most connections one IP held.
# v5.84 (#606, Tom 2026-11-10: phase 1 of cheat detection, "flag and hold,
# never auto-ban"): held results (t1 WTT week, t2 gap to the fastest other
# time, t4 WTT ghost, t6 WTT stock PR; Times.hold_reasons), owner-only via
# Times.hide_kind "held" with the previous best still shown to others,
# released by the T2 re-check or the T4 ghost, approved / rejected by
# `approve|reject member N event E time T` in --lb-banned or on the site's
# Admin tab (/prr/api/admin/held, --lb-admins); --held-report; --lb-testers
# (owner and friends only, no prize); --no-lb-holds. Held WTT times are left
# out of the prize list until released. OMP: forfeit wins show no time (O4);
# report disagreement (O2) and late / early finish reports (O3) mark the
# record "disputed", never rated.
# v5.85 (#644): --news FILE, a server-side popup broadcast through the news
# room sync 10748 (no build needed): each message in the JSON file (id,
# title, text, start/end, targets: build_below, builds, not_builds,
# members, not_members, platform) is sent as a one-time popup item (type 2,
# flag_a0 1, id 0x20000000 + id) to the players it targets. The file is
# re-read when it changes (no restart); a bad file keeps the last good one.
# One 10748 answer now merges the broadcast, --news-test and the OMP invite
# popups (before: the test file or the invites). With --news,
# /prr/api/status adds "news": members sent each message id (since the
# start; sent, not shown).
# v5.86 (#606 phase 2, Tom 2026-11-11 "phase 2 items 1-3 go"): per-track
# minimum lap times, --lb-floors (CSV kind,key,floor_ms; data/lb-floors.csv,
# re-read when it changes) with --event-index (event -> track): a new Time
# Trial best under its track's floor is held (t3, admin only); an OMP
# finished time under laps x the track's floor is DNF (O1), on top of
# v5.82's 30 s a lap, logged at settle "(under the track minimum: N ms)".
# --floors-suggest OUT writes a suggested table (0.9 x the fastest trusted
# lap, 5+ trusted times per track: ghost-backed, not held, no banned /
# blocked / testers; OMP: public rooms with 2+ finishers, not disputed or a
# forfeit) for an admin to check and copy. T5, log only: a newly kept
# ghost's path / lap more than 10% over the event's median, or its path
# 10% shorter, gets a "ghost speed member M event E: ..." line (index
# "path", computed on first use).
VERSION = "5.86"

import argparse
import base64
import bisect
import csv
import datetime
import hashlib
import hmac
import http.cookies
import http.server
import json
import math
import os
import re
import secrets
import shutil
import socket
import statistics
import struct
import sys
import threading
import time
import urllib.parse
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import rr3_cc_blob as blob
except ImportError:
    blob = None
try:
    import rr3_attest                       # v5.38 (#204); needs the cryptography package
except ImportError:
    rr3_attest = None
from rr3_build_policy import AdmitFile, Blocklist, BuildAllowlist, BuildGate, BUILD_TAG_TEXT_RE, ip_key

class TimedLock:
    """The server lock (v5.83, #248): a plain Lock that also adds up, per
    thread, how long its holder waited for it, for the request timing."""

    def __init__(self):
        self._lock = threading.Lock()
        self._local = threading.local()

    def acquire(self, *args, **kw):
        t = time.monotonic()
        got = self._lock.acquire(*args, **kw)
        self._local.wait = getattr(self._local, "wait", 0.0) + time.monotonic() - t
        return got

    def release(self):
        self._lock.release()

    def locked(self):
        return self._lock.locked()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()

    def take_wait(self):
        """Seconds this thread waited for the lock since the last call."""
        w = getattr(self._local, "wait", 0.0)
        self._local.wait = 0.0
        return w


lock = TimedLock()
count = [0]

def load_server_key(path):
    """Load the persistent HMAC secret, creating it if necessary."""
    try:
        with open(path, "rb") as f:
            key = f.read()
    except FileNotFoundError:
        key = secrets.token_bytes(32)
        try:
            with open(path, "xb") as f:
                f.write(key)
        except FileExistsError:
            with open(path, "rb") as f:
                key = f.read()

    if len(key) != 32:
        raise ValueError(f"Server key file must contain exactly 32 bytes: {path}")

    return key


def private_player_key(server_key, identifier_type, identifier):
    """Return a stable, keyed pseudonym for a player identifier."""
    message = f"rr3-player-v1:{identifier_type}:{identifier}".encode("utf-8")
    digest = hmac.new(server_key, message, hashlib.sha256).hexdigest()
    return "h:" + digest

# Fields confirmed on screen (2026-10-14): s1 name, s5 tag in [brackets],
# i8c car id, time = PR shown, i84 rank, i88 lap time in ms. Others are
# still labels.
# Leaderboard groups (10484): an empty group list crashed the groups tab
# (array[-1] at 0xce16ac, 2026-10-14), so one band is always sent (v5.30):
# GROUP ALL TOP 100%, rank cutoff = entries + 1 (everyone), second cutoff 0.
# Kept separate so the WTT reward bands (#193) can replace it.
GROUP_NAME = "ALL"


def groups_reply(entries):
    """10484 answer: one band holding every entry of the event."""
    return blob.u32(0, 0, 1) + blob.string(GROUP_NAME) + struct.pack("<f", 100.0) + blob.u32(entries + 1, 0)


# v5.76 (#193): the bands of ttc_rewards_primary_640 (ttr.dat), best first,
# in tenths of a percent; band i of the 10484 answer = reward tier i
# (analysis/weekly-time-trial.md 5.1 and 7).
COMP_BANDS = (1, 15, 50, 100, 250, 500, 750, 1000)
COMP_FIRST_WORD = 5             # 10484 / 10477 payload word 0 of a competition (WTT/TTC)


def band_name(tenths):
    return f"TOP {tenths // 10}%" if tenths % 10 == 0 else f"TOP {tenths // 10}.{tenths % 10}%"


def competition_bands(times_ms):
    """[(name, percent, rank cutoff, lap cutoff)] for an event whose entries
    have these lap times (best first): rank cutoff = ceil(percent / 100 x
    entries), at least 1; lap cutoff = the lap time at that rank (the last
    one when there are fewer entries), 0 with no entry."""
    n, out = len(times_ms), []
    for b in COMP_BANDS:
        cut = max(1, -(-b * n // 1000))
        out.append((band_name(b), b / 10, cut, times_ms[min(cut, n) - 1] if n else 0))
    return out


def competition_groups_reply(times_ms):
    """10484 answer for a competition: the 8 reward bands (v5.76, #193)."""
    bands = competition_bands(times_ms)
    return blob.u32(0, 0, len(bands)) + b"".join(
        blob.string(name) + struct.pack("<f", pct) + blob.u32(cut, lap) for name, pct, cut, lap in bands)


def group_answer(payload, times, key):
    """10484 answer for its own event: 8 bands for a competition, else ALL."""
    rows = times.rows(group_request(payload), key)[0]
    if len(payload) >= 4 and struct.unpack_from("<I", payload, 0)[0] == COMP_FIRST_WORD:
        return competition_groups_reply([r["i88"] for r in rows])
    return groups_reply(len(rows))


PENDING_SECRETS_MAX = 10000     # v5.57: secrets of refused syncs kept in memory (oldest dropped)

ASSET_LIST = "asset_list_updates.txt"
ASSET_PREFIX = "/rr3/live/asset_list_updates"
ASSET_HASH_MOD = 0x106D643D


def asset_hash(path):
    """Pack entry hash of a list path (0x1cd0c00): djb2 over the signed
    bytes, 32-bit, mod 0x106d643d."""
    h = 5381
    for c in path.encode():
        h = (h * 33 + (c - 256 if c > 127 else c)) & 0xFFFFFFFF
    return h % ASSET_HASH_MOD


class AssetUpdate:
    """--asset-update DIR (v5.31): the update list, its pack and the 10449
    answer, rebuilt when a file under DIR changes."""

    def __init__(self, root):
        self.root, self.sig, self.checked = root, None, 0.0
        self.files, self.list_text, self.list_md5, self.pack = [], b"", "", b""

    def refresh(self):
        if time.time() - self.checked < 1:
            return
        self.checked = time.time()
        found = []
        for d, _dirs, names in os.walk(self.root):
            for n in names:
                full = os.path.join(d, n)
                st = os.stat(full)
                found.append(("/" + os.path.relpath(full, self.root).replace(os.sep, "/"),
                              full, st.st_mtime_ns, st.st_size))
        found.sort()
        sig = [(g, m, z) for g, _f, m, z in found]
        if sig == self.sig:
            return
        files = []
        for game, full, _m, _z in found:
            with open(full, "rb") as f:
                data = f.read()
            body = b"FMASZ1" + zlib.compress(data, 9)
            files.append(dict(path=game, body=body, md5=hashlib.md5(body).hexdigest(), size=len(data)))
        self.files, self.sig = files, sig
        self.list_text = "".join(f"{f['path']}\t{f['md5']}\t{len(f['body'])}\t{f['size']}\n"
                                 for f in files).encode()
        self.list_md5 = hashlib.md5(self.list_text).hexdigest() if files else ""
        self.pack = b"".join(struct.pack("<II", asset_hash(f["path"]), len(f["body"])) + f["body"]
                             for f in files)
        print(f"[----] asset update: {len(files)} file(s), list {self.list_md5 or '-'}: "
              + ", ".join(f"{f['path']} {f['md5']}" for f in files), flush=True)

    def reply_10449(self, member=None):
        """(payload, log text) or (None, text) when there is nothing to offer.
        `member` is ignored here (AssetSets uses it, v5.35)."""
        self.refresh()
        if not self.files:
            return None, "no asset update"
        return blob.string(ASSET_LIST) + blob.string(self.list_md5), f"asset update {self.list_md5}"

    def get(self, url_path):
        """Body for a GET under ASSET_PREFIX, or None (404)."""
        p = re.sub(r"/+", "/", url_path.split("?")[0])
        m = re.fullmatch(re.escape(ASSET_PREFIX) + r"[^/]*/([0-9a-f]{32})\.(txt|bin)", p)
        if not m:
            return None
        self.refresh()
        md5, ext = m.groups()
        # Every download starts with u32 hash(name) + u32 length, a single
        # .txt file too (v5.32; v5.31's bare list failed the hash check).
        if md5 == self.list_md5 and self.files:
            if ext == "bin":
                return self.pack
            return struct.pack("<II", asset_hash(ASSET_LIST), len(self.list_text)) + self.list_text
        f = next((f for f in self.files if f["md5"] == md5), None)
        if f is None:
            return None
        return struct.pack("<II", asset_hash(f["path"]), len(f["body"])) + f["body"]


class AssetSets:
    """--asset-update DIR plus, since v5.35 (issue #311), --asset-test DIR
    for the members listed in --asset-testers FILE (one member id per line,
    # starts a comment; read again when the file changes). A listed member
    gets the test set's 10449 answer, everyone else the normal one. Both
    sets' files are served (they are told apart by md5)."""

    def __init__(self, main_dir=None, test_dir=None, testers_path=None):
        self.main = AssetUpdate(main_dir) if main_dir else None
        self.test = AssetUpdate(test_dir) if test_dir else None
        self.testers_path, self.testers, self.testers_sig = testers_path, set(), None

    def tester_ids(self):
        p = self.testers_path
        try:
            st = os.stat(p) if p else None
        except OSError:
            st = None
        sig = (st.st_mtime_ns, st.st_size) if st else None
        if sig != self.testers_sig:
            ids = set()
            if st:
                for line in open(p).read().splitlines():
                    line = line.split("#")[0].strip()
                    if line.isdigit():
                        ids.add(int(line))
            self.testers, self.testers_sig = ids, sig
        return self.testers

    def reply_10449(self, member=None):
        if self.test and member in self.tester_ids():
            r, info = self.test.reply_10449()
            return r, info.replace("asset update", "asset update test", 1)
        if self.main:
            return self.main.reply_10449()
        return None, "no asset update"

    def get(self, url_path):
        for s in (self.test, self.main):
            body = s.get(url_path) if s else None
            if body is not None:
                return body
        return None


def byte_range(header, size):
    """(start, end) of a 'bytes=a-b' Range header within size, or None."""
    m = re.fullmatch(r"\s*bytes=(\d*)-(\d*)\s*", header or "")
    if not m or m.group(1) == m.group(2) == "":
        return None
    if m.group(1) == "":
        start, end = max(0, size - int(m.group(2))), size - 1
    else:
        start = int(m.group(1))
        end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
    return (start, end) if start <= end < size else None


def group_request(payload):
    """10484 payload: u32 0 (5 for a competition), u32 1, u32 event id, u32 -1."""
    return struct.unpack_from("<I", payload, 8)[0]
# Member ids: 1 is the game's "no member" (fixed 1 at 0x600f30, inferred),
# sent when the request has no player key; players get ids from FIRST_MEMBER.
NO_MEMBER = 1
FIRST_MEMBER = 1000
# A stored result must have a car id >= 0 and a PR in this range (issue
# #143: NaN or infinity reached other phones). Loose: the real range of car
# ids and PRs is not checked yet.
PR_MAX = 1000.0
TIME_MAX_MS = 30 * 60 * 1000    # longest Time Trial lap kept (v5.45; real laps are well under 15 min)
# Events kept off the leaderboards: 18130 = every Debug Race Selector race
# (series 9995), whatever the track and car (issue #153).
IGNORED_EVENTS = frozenset([18130])
# Fake-player caps (v5.12, issue #143 item 6). A new player is a new player
# key (Android id); each gets a member id kept for ever.
NEW_PLAYERS_PER_IP = 10         # new players one IP may add per NEW_PLAYER_WINDOW_S (0 = no cap)
NEW_PLAYER_WINDOW_S = 3600
NEW_PLAYER_IPS_MAX = 10000      # IPs remembered for the cap (oldest forgotten first)
LB_ROWS = 100                   # leaderboard rows sent (the fastest), plus the asking player's own
# v5.84 (#606): held results. A new best that breaks a rule is stored but
# shown to its owner only (others see the owner's previous best, if any),
# never mailed and never paid, until it is released (rule no longer
# applies), approved or rejected by an admin.
HOLD_WTT_GRACE_S = 6 * 3600     # T1: a WTT time may arrive this long after the WTT's end
HOLD_GAP = 0.93                 # T2: held when under HOLD_GAP x the fastest other visible time...
HOLD_GAP_FIELD = 5              # ...on an event with at least this many visible entries (the new one counted)
HOLD_PR_TOL = 0.05              # T6: a WTT PR this far from the event's usual PR for the car is held...
HOLD_PR_MIN = 3                 # ...once at least this many other visible entries have the car
PREV_FIELDS = ("name", "time_ms", "car", "pr", "date", "t")    # a held time's kept previous best
HOLD_REASONS = {                # code -> text for the log, --held-report and the admin page
    "t1": "outside the WTT's week",
    "t2": "more than 7% under the fastest other time",
    "t3": "under the track's minimum lap time",
    "t4": "WTT time without a matching ghost",
    "t6": "PR differs from the WTT's stock PR for the car",
}


class Floors:
    """v5.86 (#606 phase 2, T3/O1): minimum lap times per track, from
    --lb-floors (CSV kind,key,floor_ms[,...]; kind "tt": key = the track
    name of tables/event-index.csv, a Time Trial lap; kind "omp": key = the
    OMP track id, one lap of a race). Made by --floors-suggest and checked
    by an admin before use. Re-read when the file changes (at most once a
    second); a missing file = no floors; a bad line is logged and skipped.
    event_index: tables/event-index.csv (event_id -> track), read once."""

    def __init__(self, path, event_index=None, log=print, clock=time.monotonic):
        self.path, self.log, self.clock = path, log, clock
        self.tt, self.omp, self.stamp, self.next_check = {}, {}, None, 0.0
        self.event_track = {}
        if event_index:
            try:
                with open(event_index, newline="", encoding="utf-8") as f:
                    for r in csv.DictReader(f):
                        try:
                            self.event_track[int(r["event_id"])] = (r.get("track") or "").strip().lower()
                        except (KeyError, ValueError, TypeError):
                            continue
            except OSError as e:
                log(f"lb-floors: event index {event_index} not read ({e}): Time Trial floors off")
        self.refresh(force=True)

    def refresh(self, force=False):
        if not self.path or (not force and self.clock() < self.next_check):
            return
        self.next_check = self.clock() + 1.0
        try:
            st = os.stat(self.path)
        except OSError:
            if self.stamp is not None:
                self.log(f"lb-floors {self.path} removed: no floors")
            self.tt, self.omp, self.stamp = {}, {}, None
            return
        if (st.st_mtime_ns, st.st_size) == self.stamp:
            return
        tt, omp = {}, {}
        try:
            with open(self.path, newline="", encoding="utf-8-sig") as f:
                for n, r in enumerate(csv.DictReader(f), 2):
                    try:
                        kind, key, ms = (r.get("kind") or "").strip().lower(), (r.get("key") or "").strip(), int(r["floor_ms"])
                        if ms <= 0 or not key or kind not in ("tt", "omp"):
                            raise ValueError
                        if kind == "tt":
                            tt[key.lower()] = ms
                        else:
                            omp[int(key)] = ms
                    except (KeyError, ValueError, TypeError):
                        self.log(f"lb-floors {self.path}: line {n} not understood, skipped")
        except (OSError, UnicodeError, csv.Error) as e:
            self.log(f"lb-floors {self.path}: {e}; keeping the last table")
            return
        self.tt, self.omp, self.stamp = tt, omp, (st.st_mtime_ns, st.st_size)
        self.log(f"lb-floors {self.path}: {len(tt)} Time Trial track(s), {len(omp)} OMP track(s)")

    def tt_floor(self, event):
        """The minimum lap (ms) of event's track, or None."""
        self.refresh()
        track = self.event_track.get(event)
        return self.tt.get(track) if track else None

    def omp_floor(self, track):
        """The minimum lap (ms) of OMP track id, or None."""
        self.refresh()
        try:
            return self.omp.get(int(track))
        except (TypeError, ValueError):
            return None


FLOORS = [None]                 # v5.86 (#606): the Floors, set by main() with --lb-floors


def result_problem(car, pr, time_ms=None, cars=None):
    """Why a result (car, PR, time) must not be stored or shown, or None.
    v5.1: car >= 0, PR a finite number 0..PR_MAX. v5.45 (issue #143 item 5):
    car an int in cars (the game's car ids, --cars) when cars is given;
    time_ms (when given) an int, 0 < time_ms <= TIME_MAX_MS."""
    if isinstance(car, bool) or not isinstance(car, int) or car < 0:
        return f"car {car!r}"
    if cars is not None and car not in cars:
        return f"car {car} not in the car list"
    if isinstance(pr, bool) or not isinstance(pr, (int, float)) or not math.isfinite(pr) \
            or not 0 <= pr <= PR_MAX:
        return f"PR {pr!r}"
    if time_ms is not None and (isinstance(time_ms, bool) or not isinstance(time_ms, int)
                                or not 0 < time_ms <= TIME_MAX_MS):
        return f"time {time_ms!r} ms"
    return None


def valid_result(car, pr, time_ms=None, cars=None):
    return result_problem(car, pr, time_ms, cars) is None


def load_cars(path):
    """The game's car ids from tables/car-index.csv (column car_id), as a
    frozenset (v5.45). Raises OSError or ValueError."""
    with open(path, newline="") as f:
        cars = frozenset(int(r["car_id"]) for r in csv.DictReader(f))
    if not cars:
        raise ValueError("no cars")
    return cars


IOS_BUILD_RE = re.compile(r"PRR i[0-9]{2,}-(?:alpha|beta|stable)\Z")


def ios_exempt_why(h, build):
    """v5.61 (#451): why this sync may NOT skip --attest-enforce as an
    iPhone ("" = it may). h is the request header (blob.header()), build the
    label the build gate allowed (None when there is no gate: then never).
    Needs an iOS build label, an IDFV (the type-1 entry only an iPhone
    sends) and a player secret. An Android or Synergy id read from the
    header doesn't matter: an iPhone's typed entries 4-6 can look like one
    (v5.59 required neither, and refused real iPhones)."""
    if not (build and IOS_BUILD_RE.match(build)):
        return "no ios label"
    if not h["idfv"]:
        return "no idfv"
    if not h["secret"]:
        return "no secret"
    return ""


def is_iphone(h, build):
    """v5.66: does this sync come from an iPhone? An IDFV (the header's
    type-1 entry, only an iPhone sends it) or an iOS build label. Unlike
    ios_exempt() no secret is needed: this only withholds things."""
    return bool(h["idfv"]) or bool(build and IOS_BUILD_RE.match(build))


ASSET_UPDATE_IOS = [False]      # v5.66: --asset-update-ios (offer the update list to iPhones too)


def ios_exempt(h, build):
    """v5.59 (#451): may this sync skip --attest-enforce as an iPhone?
    See ios_exempt_why()."""
    return not ios_exempt_why(h, build)


def player_key(plain, server_key):
    """Return a private, stable key for the requesting player."""
    h = blob.header(plain)
    if h["android_id"]:
        return private_player_key(server_key, "a", h["android_id"])
    if h["synergy_id"]:
        return private_player_key(server_key, "s", h["synergy_id"])
    if h["idfv"]:                   # v5.46 (#299): an iPhone
        return private_player_key(server_key, "i", h["idfv"])
    return "unknown"


def trusted_digest(text):
    """A --trusted-sig value as 64 lowercase hex digits: accepts the
    keytool / apksigner forms (upper case, colons, spaces). None if bad."""
    d = re.sub(r"[\s:]", "", text).lower()
    return d if blob.SIG_RE.fullmatch(d) else None


SIG_NAME_RE = re.compile(r"[A-Za-z0-9_.-]{1,32}")


class TrustedSigs:
    """Trusted APK signing keys: digest -> name. From --trusted-sigs FILE
    (one "name digest" per line, # comments; v5.29) and --trusted-sig
    (named "trusted"). The file is re-read when its mtime changes (checked
    at most once a second); a file that no longer parses keeps the old
    list and says so. Names "unknown" and "other..." are refused (they would
    read as the untrusted labels)."""

    def __init__(self, cli=(), path=None):
        self.cli = {d: "trusted" for d in cli}
        self.path, self.mtime, self.checked, self.file = path, None, 0.0, {}
        if path:
            self.file = self.read(path)
            self.mtime = os.stat(path).st_mtime

    @staticmethod
    def read(path):
        out = {}
        for n, line in enumerate(open(path, encoding="utf-8"), 1):
            line = line.split("#", 1)[0].split()
            if not line:
                continue
            if len(line) != 2:
                raise ValueError(f"{path}:{n}: expected 'name digest'")
            name, d = line[0], trusted_digest(line[1])
            if not SIG_NAME_RE.fullmatch(name) or name == "unknown" or name.startswith("other"):
                raise ValueError(f"{path}:{n}: bad name {name!r} (A-Z a-z 0-9 _ . -, not unknown/other)")
            if d is None:
                raise ValueError(f"{path}:{n}: not a SHA-256 (64 hex digits, colons allowed)")
            if d in out:
                raise ValueError(f"{path}:{n}: digest listed twice")
            out[d] = name
        return out

    def refresh(self):
        if not self.path or time.time() - self.checked < 1:
            return
        self.checked = time.time()
        try:
            m = os.stat(self.path).st_mtime
            if m != self.mtime:
                self.file, self.mtime = self.read(self.path), m
                print(f"trusted APK signatures re-read: {self.names()}", flush=True)
        except (OSError, ValueError) as e:
            self.mtime = None if isinstance(e, OSError) else self.mtime
            print(f"trusted APK signatures: {e}; keeping the old list", flush=True)

    def get(self, sig):
        self.refresh()
        return self.file.get(sig) or self.cli.get(sig)

    def __len__(self):
        return len(set(self.file) | set(self.cli))

    def names(self):
        return ", ".join(sorted(set(self.file.values()) | ({"trusted"} if self.cli.keys() - self.file.keys() else set())))


def apk_label(sig, trusted):
    """Label for a request's header sig (blob.header()["sig"]): the trusted
    key's name (v5.29; "devel" before), "other (...)" or "unknown". Log
    only (issue #143). trusted: TrustedSigs or a dict digest -> name."""
    if not sig:
        return "unknown"
    name = trusted.get(sig) if trusted else None
    if name:
        return name
    return "other (sig:none)" if sig == "none" else f"other (sig {sig[:8]}..)"


class Times:
    """Best Time Trial time per event and player, kept in a JSON file:
    {"<event>": {"<player key>": {"name": .., "time_ms": .., "car": .., "pr": .., "date": ..}}}
    The player key comes from player_key(). Names: --names file
    {"<Android id, Synergy id or player key>": "<name>"}, else the
    player's in-game username (--usernames file {"<player key>": "<name>"}),
    else --name if given, else "Racer " + the key's last 4 characters.
    Member ids: --members file {"next": .., "members": {"<player key>": id}}.
    events: the event ids results may be stored for (--events), None = any.
    new_per_ip: NEW_PLAYERS_PER_IP (0 = no cap).
    Shadowed players (v5.13, --shadowed file: a JSON list of player keys)
    are hidden from everyone else when shadow_other is on.
    cars: the game's car ids (--cars, v5.45), None = any car >= 0. Stored
    entries that fail result_problem() are taken out at start (v5.45, see
    check_stored)."""

    def __init__(self, path, name, tag, rivals, skip_queued=False, names_path=None, server_key=None,
                 usernames_path=None, members_path=None, mail=None, events=None,
                 new_per_ip=NEW_PLAYERS_PER_IP, shadow_path=None, shadow_other=False, cars=None,
                 claims_path=None):
        self.path, self.name, self.tag, self.rivals = path, name, tag, rivals
        self.cars = cars
        self.shadow_path, self.shadow_other = shadow_path, shadow_other
        # v5.80 (#607): leaderboard ban. lb_banned: member ids (a HiddenList
        # or any container); blocklist: rr3_build_policy.Blocklist or None
        # (its members are hidden too); friends: Friends, for the ban's
        # friends exception. main() sets them.
        self.lb_banned, self.blocklist, self.friends = frozenset(), None, None
        # v5.84 (#606): held results. testers: member ids (--lb-testers);
        # holds: the hold rules on (--no-lb-holds turns them off); wtt:
        # event -> (start, end) unix seconds of a WTT, or None (PrizeList);
        # ghosts: Ghosts, for T4 (a matching ghost) and a rejected time's
        # ghost; admins: member ids allowed on the admin page (--lb-admins).
        # notes: what the last add_history held or released, for the log.
        self.testers, self.admins, self.holds = frozenset(), frozenset(), True
        self.wtt, self.ghosts, self.notes = None, None, []
        try:
            self.shadowed = set(json.load(open(shadow_path))) if shadow_path else set()
        except FileNotFoundError:
            self.shadowed = set()
        self.events = events
        self.new_per_ip = new_per_ip
        self.new_by_ip = {}             # IP -> times (s) it added a new player, last NEW_PLAYER_WINDOW_S
        self.names_cache = (None, {})   # (--names file mtime, its contents)
        self.mail = mail
        self.skip_queued = skip_queued
        self.names_path = names_path
        self.server_key = server_key
        self.usernames_path = usernames_path
        try:
            self.usernames = json.load(open(usernames_path)) if usernames_path else {}
        except FileNotFoundError:
            self.usernames = {}
        self.skipped = set()
        try:
            self.data = json.load(open(path))
        except FileNotFoundError:
            self.data = {}
        self.check_stored()
        self.members_path = members_path
        try:
            m = json.load(open(members_path)) if members_path else {}
        except FileNotFoundError:
            m = {}
        self.members = m.get("members", {})
        self.next_member = max([m.get("next", FIRST_MEMBER), FIRST_MEMBER]
                               + [i + 1 for i in self.members.values()])
        self.by_member = {i: k for k, i in self.members.items()}
        self.assign_existing()
        self.load_claims(claims_path)

    def entry_problem(self, e):
        """Why a stored entry must not be kept, or None (v5.45)."""
        if not isinstance(e, dict):
            return f"not an entry: {type(e).__name__}"
        missing = [f for f in ("car", "pr", "time_ms") if f not in e]
        if missing:
            return "missing " + ", ".join(missing)
        return result_problem(e["car"], e["pr"], e["time_ms"], self.cars)

    def check_stored(self):
        """v5.45 (issue #143 item 5): take every stored entry that fails
        entry_problem() out of the times file. Before the first rewrite the
        file is copied to <file>.bak-v5.45 (kept, never overwritten); the
        entries taken out are added to <file>.rejected.json with the reason
        and logged. Returns how many."""
        bad = []
        if not isinstance(self.data, dict):
            raise SystemExit(f"{self.path}: not a times file (a JSON object of events)")
        for event, ev in list(self.data.items()):
            if not isinstance(ev, dict):
                bad.append(dict(event=event, key=None, entry=ev, why="not an event table"))
                del self.data[event]
                continue
            for k, e in list(ev.items()):
                why = self.entry_problem(e)
                if why:
                    bad.append(dict(event=event, key=k, entry=e, why=why))
                    del ev[k]
        if not bad:
            return 0
        backup = f"{self.path}.bak-v{VERSION}"
        if not os.path.exists(backup):
            shutil.copy2(self.path, backup)
        rejected_path = self.path + ".rejected.json"
        try:
            rejected = json.load(open(rejected_path))
        except FileNotFoundError:
            rejected = []
        today = datetime.date.today().isoformat()
        for b in bad:
            who = b["key"] if b["key"] is None or ":" not in b["key"] else f"{b['key'][2:6]}..{b['key'][-4:]}"
            print(f"time {b['event']} {who} rejected: {b['why']}", flush=True)
            rejected.append(dict(b, date=today, version=VERSION))
        tmp = rejected_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(rejected, f, indent=1)
        os.replace(tmp, rejected_path)
        self.save()
        print(f"times: {len(bad)} stored entr{'y' if len(bad) == 1 else 'ies'} rejected, kept in "
              f"{rejected_path} (original file: {backup})", flush=True)
        return len(bad)

    def result_problem(self, r):
        """Why a 10451 Time Trial result must not be stored, or None."""
        return result_problem(r["car"], r["pr"], r["time_ms"], self.cars)

    def assign_existing(self):
        """Give a member id to every player key in the times file that has
        none, oldest first (earliest date). Old entries keyed by name are
        skipped."""
        first = {}
        for ev in self.data.values():
            for k, e in ev.items():
                if ":" in k and k not in self.members:
                    d = e.get("date", "9999")
                    first[k] = min(first.get(k, d), d)
        for k in sorted(first, key=lambda k: (first[k], k)):
            self.add_member(k, save=False)
        if first:
            self.save_members()

    def add_member(self, key, save=True):
        i = self.next_member
        self.next_member += 1
        self.members[key] = i
        self.by_member[i] = key
        if save:
            self.save_members()
        return i

    def allow_new(self, key, ip, now=None):
        """False when key is a new player and ip already added new_per_ip
        new players in the last NEW_PLAYER_WINDOW_S (v5.12); else True,
        counting key against ip if it is new."""
        if not self.new_per_ip or not ip or key == "unknown" or key in self.members:
            return True
        now = time.time() if now is None else now
        recent = [t for t in self.new_by_ip.get(ip, []) if now - t < NEW_PLAYER_WINDOW_S]
        if len(recent) >= self.new_per_ip:
            self.new_by_ip[ip] = recent
            return False
        self.new_by_ip.pop(ip, None)
        self.new_by_ip[ip] = recent + [now]     # re-inserted: dict order = least recent first
        while len(self.new_by_ip) > NEW_PLAYER_IPS_MAX:
            del self.new_by_ip[next(iter(self.new_by_ip))]
        return True

    def set_shadowed(self, key, on):
        """Shadow key (its latest request came from an "other" APK) or
        make it visible again; saved when it changes."""
        if key == "unknown" or (key in self.shadowed) == on:
            return
        (self.shadowed.add if on else self.shadowed.discard)(key)
        if self.shadow_path:
            os.makedirs(os.path.dirname(os.path.abspath(self.shadow_path)), exist_ok=True)
            tmp = self.shadow_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(sorted(self.shadowed), f, indent=1)
            os.replace(tmp, self.shadow_path)

    def member_banned(self, member):
        """v5.80 (#607): why member is banned from the leaderboards
        ("lb-banned" or "blocklist"), else None."""
        if not member or member == NO_MEMBER:
            return None
        if member in self.lb_banned:
            return "lb-banned"
        if self.blocklist is not None and self.blocklist.member(member):
            return "blocklist"
        return None

    def banned(self, key):
        """member_banned() for a player key."""
        return self.member_banned(self.members.get(key))

    def tester(self, key):
        """v5.84 (#606): True when player key's member is on --lb-testers."""
        m = self.members.get(key)
        return bool(m) and m != NO_MEMBER and m in self.testers

    def prize_block(self, key):
        """Why player key gets no WTT prize (withheld, never paid): "lb-banned",
        "blocklist" (v5.80, #607) or "tester" (v5.84, #606); else None."""
        return self.banned(key) or ("tester" if self.tester(key) else None)

    def held(self, key, event):
        """v5.84 (#606): the hold reasons of player key's stored time on
        event ([] = not held)."""
        e = self.data.get(str(event), {}).get(key)
        return list(e.get("held") or []) if isinstance(e, dict) else []

    def hide_kind(self, key, viewer, event=None):
        """Why player key's data is hidden from viewer (a player key; None
        = the public): None (shown), "shadow" (v5.13, --shadow-other),
        "ban" (v5.80, #607), "tester" (v5.84, #606: --lb-testers) or, with
        an event, "held" (v5.84, #606: that time is held). The owner always
        sees their own."""
        if key == viewer:
            return None
        if self.shadow_other and key in self.shadowed:
            return "shadow"
        if self.banned(key):
            return "ban"
        if self.tester(key):
            return "tester"
        if event is not None and self.held(key, event):
            return "held"
        return None

    def hidden(self, key, viewer, friends_ok=False, event=None):
        """True when player key's data must not be shown to viewer. With
        friends_ok (the friends' views), a banned player (Tom, #607) or a
        tester (v5.84) stays visible to their PRR friends; a shadowed one
        or a held time (owner only, #606) does not."""
        kind = self.hide_kind(key, viewer, event)
        if kind in ("ban", "tester") and friends_ok and viewer and self.friends is not None \
                and self.friends.are_friends(key, viewer):
            return False
        return kind is not None

    def shown(self, key, e, viewer, friends_ok=False, event=None):
        """v5.84 (#606): the entry of player key on event that viewer sees:
        e itself, the previous best kept with a held time (e["prev"]), or
        None (hidden)."""
        kind = self.hide_kind(key, viewer, event)
        if kind == "held":
            p = e.get("prev")
            if not p or self.hidden(key, viewer, friends_ok):   # the member itself may be hidden too
                return None
            return p
        if kind in ("ban", "tester") and friends_ok and viewer and self.friends is not None \
                and self.friends.are_friends(key, viewer):
            return self.shown_own(e)
        return None if kind is not None else e

    @staticmethod
    def shown_own(e):
        """A friend of a banned player or tester sees their entry, but a
        held time still only as its previous best."""
        if e.get("held"):
            return e.get("prev")
        return e

    def known(self, event):
        return self.events is None or event in self.events

    def member_id(self, key):
        """The player's member id, assigned on first contact; NO_MEMBER
        for a request without a player key."""
        if key == "unknown":
            return NO_MEMBER
        return self.members.get(key) or self.add_member(key)

    def save_members(self):
        if not self.members_path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.members_path)), exist_ok=True)
        tmp = self.members_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"next": self.next_member, "members": self.members}, f, indent=1, sort_keys=True)
        os.replace(tmp, self.members_path)

    def names_key(self, k):
        """A --names key as a player key: an Android id (16 hex digits), a
        Synergy id (all digits) or (v5.46) an iPhone IDFV (a UUID) goes
        through private_player_key() as in player_key(); a player key is
        kept."""
        if self.server_key and re.fullmatch(r"[0-9a-f]{16}", k):
            return private_player_key(self.server_key, "a", k)
        if self.server_key and re.fullmatch(r"[0-9]{8,20}", k):
            return private_player_key(self.server_key, "s", k)
        if self.server_key and blob.UUID_RE.fullmatch(k):     # v5.46: an iPhone's IDFV
            return private_player_key(self.server_key, "i", k.upper())
        return k

    def names(self):
        """The --names file, re-read only when it changes (edits apply
        without a restart; v5.12 no longer reads it once per row)."""
        if not self.names_path:
            return {}
        try:
            mtime = os.stat(self.names_path).st_mtime_ns
        except OSError:
            return {}
        if mtime != self.names_cache[0]:
            try:
                self.names_cache = (mtime, json.load(open(self.names_path)))
            except (OSError, ValueError):
                self.names_cache = (mtime, {})
        return self.names_cache[1]

    def display_name(self, key):
        for k, v in self.names().items():
            if self.names_key(k) == key:
                return str(v)[:24]
        if key in self.usernames:
            return self.usernames[key]
        return self.name or "Racer " + key[-4:]

    def set_username(self, key, username):
        """Keep the in-game username a request carries ("" = none: the
        player cleared it, or the lib has no rr3_username.py patch).
        v5.74 (#178): the name is claimed for the player's member id; a
        name held by another member (or a --names value of another
        player) is kept as "Name (N)". Returns a log note ("" if none)."""
        if key == "unknown":
            return ""
        member = self.member_id(key)
        shown, note = self.claim(member, username, key)
        changed = self.claims_dirty
        if self.usernames.get(key) != shown:
            if shown:
                self.usernames[key] = shown
            else:
                del self.usernames[key]
            self.save_usernames()
        if changed:
            self.save_claims()
        return note

    def save_usernames(self):
        if self.usernames_path:
            os.makedirs(os.path.dirname(os.path.abspath(self.usernames_path)), exist_ok=True)
            tmp = self.usernames_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.usernames, f, indent=1, sort_keys=True)
            os.replace(tmp, self.usernames_path)

    def load_claims(self, path):
        """v5.74 (#178): --username-claims {"claims": {"<name, lower case>":
        {"member": id, "name": spelling, "since": "YYYY-MM-DD"}},
        "taken": {"<member>": "<name chosen but held by another>"}}. When
        the file is missing, it is built from --usernames, lowest member id
        first (the oldest player keeps a duplicated name)."""
        self.claims_path = path
        self.claims, self.taken, self.claims_dirty = {}, {}, False
        try:
            d = json.load(open(path)) if path else None
        except FileNotFoundError:
            d = None
        if d is not None:
            self.claims = {n: c for n, c in d.get("claims", {}).items()
                           if isinstance(c, dict) and isinstance(c.get("member"), int)}
            self.taken = {int(m): n for m, n in d.get("taken", {}).items() if str(m).isdigit()}
            self.claimed_by = {c["member"]: n for n, c in self.claims.items()}
            return
        self.claimed_by = {}
        wanted = dict(self.usernames)
        order = sorted(wanted, key=lambda k: (self.members.get(k, 1 << 62), k))
        for k in order:
            if k in self.members:
                self.usernames[k], _ = self.claim(self.members[k], wanted[k], k)
        if order:
            self.save_usernames()
        self.save_claims()
        if path:
            print(f"username claims built: {len(self.claims)} names, {len(self.taken)} shown with a suffix",
                  flush=True)

    def save_claims(self):
        self.claims_dirty = False
        if not self.claims_path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.claims_path)), exist_ok=True)
        tmp = self.claims_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"claims": self.claims, "taken": {str(m): n for m, n in self.taken.items()}},
                      f, indent=1, sort_keys=True)
        os.replace(tmp, self.claims_path)

    def admin_owner(self, low):
        """The player key whose --names value is low (lower case), or None."""
        for k, v in self.names().items():
            if str(v)[:24].lower() == low:
                return self.names_key(k)
        return None

    def claim(self, member, username, key):
        """The name to show for member (who sent username; "" = none) and a
        log note; updates the claims in memory (claims_dirty)."""
        low = username.lower()
        old = self.claimed_by.get(member)
        if old is not None and old != low:              # a rename or a cleared name frees the old one
            del self.claims[old]
            del self.claimed_by[member]
            self.claims_dirty = True
        if not username:
            if self.taken.pop(member, None) is not None:
                self.claims_dirty = True
            return None, ""
        holder = self.claims.get(low)
        if holder and holder["member"] != member and holder["member"] not in self.by_member:
            del self.claims[low]                        # its member is gone: free
            self.claimed_by.pop(holder["member"], None)
            holder = None
        admin = self.admin_owner(low)
        if (admin is not None and admin != key) or (holder and holder["member"] != member):
            if self.taken.get(member) != username:
                self.taken[member] = username
                self.claims_dirty = True
            return self.suffixed(username, key), f"name {username} taken"
        if self.taken.pop(member, None) is not None:
            self.claims_dirty = True
        if holder is None or holder["name"] != username:
            self.claims[low] = {"member": member, "name": username,
                                "since": (holder or {}).get("since") or datetime.date.today().isoformat()}
            self.claimed_by[member] = low
            self.claims_dirty = True
        return username, ""

    def suffixed(self, username, key):
        """username + " (N)", N >= 2, unique among the names shown; the
        player's current one is kept if it still fits."""
        mine = self.usernames.get(key, "")
        if re.fullmatch(re.escape(username) + r" \(\d+\)", mine):
            return mine
        used = {v.lower() for k, v in self.usernames.items() if k != key}
        n = 2
        while f"{username} ({n})".lower() in used:
            n += 1
        return f"{username} ({n})"

    def name_taken(self, key):
        """The name the player chose while it is held by someone else, or
        None (v5.74, for GET /prr/api/me)."""
        return self.taken.get(self.members.get(key, 0))

    def claim_old(self, key):
        """Times stored before player keys are keyed by name; with --name,
        hand the ones under that name to the first player key that asks
        (the phone server's own player)."""
        if not self.name or getattr(self, "claimed", False):
            return
        self.claimed = True
        moved = 0
        for ev in self.data.values():
            old = ev.pop(self.name, None)
            if old and (key not in ev or old["time_ms"] < ev[key]["time_ms"]):
                ev[key] = dict(old, name=self.name)
                moved += 1
        if moved:
            self.save()

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=1, sort_keys=True)
        os.replace(tmp, self.path)

    def add_history(self, payload, key, now=None):
        """Store new bests from a result upload (10451) of player key.
        Returns how many. v5.84 (#606): a new best that breaks a hold rule
        (hold_reasons) is stored held: shown to its owner only, others keep
        seeing the previous best (kept in "prev"), no mail; self.notes says
        what was held or released."""
        now = time.time() if now is None else now
        new = mailed = 0
        self.notes = []
        touched = set()
        name = self.display_name(key)
        for r in blob.race_history(payload):
            if (r["mode"] != blob.MODE_TIME_TRIAL
                    or r["event"] in IGNORED_EVENTS or not self.known(r["event"])
                    or self.result_problem(r)):
                continue
            ev = self.data.setdefault(str(r["event"]), {})
            old = ev.get(key)
            if old is None or r["time_ms"] < old["time_ms"]:
                why = self.hold_reasons(r["event"], key, r["time_ms"], r["car"], r["pr"], now)
                visible = old.get("prev") if old and old.get("held") else old
                if self.mail and not why:
                    mailed += self.mail_passed(ev, key, visible, r)
                entry = dict(name=name, time_ms=r["time_ms"], car=r["car"], pr=round(r["pr"], 2),
                             date=datetime.date.today().isoformat(), t=int(now))
                if why:                     # v5.84 (#606)
                    entry.update(held=why, held_at=int(now))
                    if visible:
                        entry["prev"] = {f: visible[f] for f in PREV_FIELDS if f in visible}
                ev[key] = entry
                if why:
                    self.note(key, r["event"], f"held: {entry['time_ms']} ms ({', '.join(why)})")
                new += 1
                touched.add(r["event"])
        for event in touched:               # v5.84: another held time's field may have caught up (T2)
            self.recheck(event, now)
        if new:
            self.save()
        if mailed:
            self.mail.save()                # once per request (v5.9; was once per mail)
        return new

    # --- v5.84 (#606): held results ---------------------------------------------
    def note(self, key, event, text):
        """Log one hold line ("held member N event E: ...") and keep it for the sync's log line."""
        line = f"member {self.members.get(key, 0)} event {event} {text}"
        self.notes.append(line)
        print(("held " if text.startswith("held") else "") + line.replace(" held:", ":"), flush=True)

    def visible_field(self, event, key=None):
        """The other players' times on event as the public sees them:
        [(time ms, car, PR)] (a held time counts as its previous best)."""
        out = []
        for k, e in self.data.get(str(event), {}).items():
            if k == key or self.entry_problem(e):
                continue
            v = self.shown(k, e, None, event=event)
            if v:
                out.append((v["time_ms"], v["car"], v.get("pr", 0)))
        return out

    def ghost_matches(self, key, event, time_ms):
        """T4: does player key have a stored ghost on event whose lap is
        time_ms? True without a ghost store (T4 off)."""
        if self.ghosts is None:
            return True
        g = self.ghosts.ghosts.get(f"{self.members.get(key, 0)}_{event}")
        return bool(g) and g.get("lap_ms") == time_ms

    def gap_held(self, event, key, time_ms, field=None):
        """T2: time_ms more than (1 - HOLD_GAP) under the fastest other
        visible time, on an event with HOLD_GAP_FIELD visible entries."""
        field = self.visible_field(event, key) if field is None else field
        return len(field) + 1 >= HOLD_GAP_FIELD and time_ms < HOLD_GAP * min(t for t, _c, _p in field)

    def hold_reasons(self, event, key, time_ms, car, pr, now):
        """The hold rules a new best breaks (#606 phase 1): t1 a WTT time
        outside the WTT's week (+HOLD_WTT_GRACE_S), t2 the gap to the
        fastest other time, t4 a WTT time without a ghost of that lap (yet:
        released when it comes), t6 a WTT PR off the usual PR for the car.
        None for a banned player or a tester (already hidden) or with the
        rules off."""
        if not self.holds or self.banned(key) or self.tester(key):
            return []
        why = []
        w = self.wtt(event) if self.wtt else None
        if w and not w[0] <= now <= w[1] + HOLD_WTT_GRACE_S:
            why.append("t1")
        field = self.visible_field(event, key)
        if self.gap_held(event, key, time_ms, field):
            why.append("t2")
        floor = FLOORS[0].tt_floor(event) if FLOORS[0] is not None else None     # v5.86 (#606 T3)
        if floor and time_ms < floor:
            why.append("t3")
        if w and not self.ghost_matches(key, event, time_ms):
            why.append("t4")
        if w:
            same = [round(p, 2) for _t, c, p in field if c == car]
            if len(same) >= HOLD_PR_MIN:
                usual = max(sorted(set(same)), key=same.count)
                if abs(round(pr, 2) - usual) > HOLD_PR_TOL:
                    why.append("t6")
        return why

    def unhold(self, key, event, codes, why):
        """Drop hold reasons codes from player key's time on event; with
        none left the time is released (shown to all). Returns True when
        released. The caller saves."""
        e = self.data.get(str(event), {}).get(key)
        if not e or not e.get("held"):
            return False
        left = [c for c in e["held"] if c not in codes]
        if left:
            e["held"] = left
            return False
        for f in ("held", "held_at", "prev"):
            e.pop(f, None)
        self.note(key, event, f"released: {e['time_ms']} ms ({why})")
        return True

    def recheck(self, event, now=None):
        """T2 again for the held times on event: a time whose field caught
        up (no longer more than 7% under the fastest other visible time)
        loses t2. Returns how many were released. The caller saves."""
        n = 0
        for k, e in list(self.data.get(str(event), {}).items()):
            if "t2" in (e.get("held") or []) and not self.gap_held(event, k, e["time_ms"]):
                if self.unhold(k, event, ("t2",), "field caught up"):
                    n += 1
                else:
                    self.note(k, event, "t2 cleared (field caught up)")
        return n

    def recheck_all(self):
        """recheck() every event with a held t2 time (at start)."""
        events = [ev for ev, rows in self.data.items() if any("t2" in (e.get("held") or []) for e in rows.values())]
        n = sum(self.recheck(int(ev)) for ev in events)
        if n:
            self.save()
        return n

    def ghost_arrived(self, member, event, lap_ms):
        """T4: a ghost of lap_ms was kept for member on event (10694)."""
        key = self.by_member.get(member)
        e = self.data.get(str(event), {}).get(key) if key else None
        if e and "t4" in (e.get("held") or []) and e["time_ms"] == lap_ms:
            self.notes = []
            if not self.unhold(key, event, ("t4",), "ghost arrived"):
                self.note(key, event, "t4 cleared (ghost arrived)")
            self.save()
            return " ".join(self.notes)
        return ""

    def admin_act(self, verb, member, event, time_ms, who):
        """approve or reject member's held time_ms on event (an admin, #606).
        approve: shown to all. reject: the time is dropped, the previous best
        (if any) comes back, and the time's ghost goes. Returns an error or
        None. Saves."""
        key = self.by_member.get(member)
        e = self.data.get(str(event), {}).get(key) if key else None
        if not e or not e.get("held") or e["time_ms"] != time_ms:
            return "no such held time"
        self.notes = []
        if verb == "approve":
            self.unhold(key, event, tuple(e["held"]), f"approved by {who}")
        elif verb == "reject":
            prev = e.get("prev")
            if prev:
                self.data[str(event)][key] = dict(prev)
            else:
                del self.data[str(event)][key]
            if self.ghosts is not None:
                self.ghosts.forget(member, event, time_ms)
            self.note(key, event, f"rejected: {time_ms} ms by {who}"
                      + (f", previous {prev['time_ms']} ms back" if prev else ""))
        else:
            return "action?"
        self.recheck(event)
        self.save()
        return None

    def apply_actions(self):
        """approve/reject lines of --lb-banned (HiddenList.actions) for held
        times that are still held: each line names the exact time, so it
        acts once and can stay in the file. Returns how many acted."""
        lst = self.lb_banned
        if hasattr(lst, "refresh"):
            lst.refresh()
        n = 0
        for verb, member, event, time_ms in sorted(getattr(lst, "actions", ())):
            key = self.by_member.get(member)
            e = self.data.get(str(event), {}).get(key) if key else None
            if e and e.get("held") and e["time_ms"] == time_ms:
                if self.admin_act(verb, member, event, time_ms, "lb-banned.txt") is None:
                    n += 1
        return n

    def held_list(self):
        """Every held time, for --held-report and the admin page: dicts with
        member, name, event, time_ms, car, pr, held (codes), held_at, prev_ms,
        field_best_ms, field_n, field_pr (min, max PR of the field's same car)
        and ghost_ms (the stored ghost's lap, or None)."""
        out = []
        for ev, rows in self.data.items():
            for k, e in rows.items():
                if not e.get("held"):
                    continue
                field = self.visible_field(int(ev), k)
                prs = [p for _t, c, p in field if c == e["car"]]
                member = self.members.get(k, 0)
                g = self.ghosts.ghosts.get(f"{member}_{ev}") if self.ghosts is not None else None
                out.append(dict(member=member, name=self.display_name(k) if ":" in k else k, event=int(ev),
                                time_ms=e["time_ms"], car=e["car"], pr=e.get("pr"), held=list(e["held"]),
                                held_at=e.get("held_at"), prev_ms=(e.get("prev") or {}).get("time_ms"),
                                field_best_ms=min((t for t, _c, _p in field), default=None),
                                field_n=len(field), field_pr=[min(prs), max(prs)] if prs else None,
                                ghost_ms=g.get("lap_ms") if g else None))
        out.sort(key=lambda h: (h.get("held_at") or 0, h["event"], h["member"]))
        return out

    def mail_passed(self, ev, key, old, r):
        """Mail the players whose best on the event the new time r of
        player key passes (was ahead of or level with key's old best): at
        most MAIL_PER_RESULT, the fastest of them (nearest the top). The
        caller saves the mail file. Returns how many were mailed. A
        shadowed (v5.13), banned (v5.80) or tester (v5.84) player mails nobody."""
        if (self.shadow_other and key in self.shadowed) or self.banned(key) or self.tester(key):
            return 0
        passed = [(e["time_ms"], k) for k, e in ev.items()
                  if k != key and ":" in k and k in self.members and self.entry_problem(e) is None
                  and r["time_ms"] < e["time_ms"] and (old is None or old["time_ms"] >= e["time_ms"])]
        passed.sort()
        for _t, k in passed[:MAIL_PER_RESULT]:
            self.mail.add(k, r["event"], key, r["time_ms"], r["car"], save=False)
        return min(len(passed), MAIL_PER_RESULT)

    def rows(self, event, key, friends_ok=False):
        """Leaderboard rows for an event and the asking player's row index.
        friends_ok (v5.80): a banned player's rows stay for their friends."""
        entries = {} if event in IGNORED_EVENTS else self.data.get(str(event), {})
        rows = []
        for k, e in entries.items():
            if self.entry_problem(e):                   # v5.1; v5.45 also car list and time
                continue
            e = self.shown(k, e, key, friends_ok, event)   # shadowed (v5.13), banned (v5.80), held (v5.84)
            if e is None:
                continue
            # entries from before player keys were keyed by name
            name = self.display_name(k) if ":" in k else k
            rows.append(dict(s1=name, i18=self.members.get(k, 0), s2="", s3="", s4="", s5=self.tag,
                             i8c=e["car"], time=e["pr"], s6="", i84=0, i88=e["time_ms"], i80=0,
                             key=k))
        rows.sort(key=lambda r: r["i88"])
        for i, r in enumerate(rows):
            r["i84"] = i                    # the game shows rank i84 + 1
        me = next((i for i, r in enumerate(rows) if r.get("key") == key), -1)
        return rows, me


GHOST_MAX = 64 << 10            # largest ghost file accepted by PUT (v5.42; largest real: 15.7 KB)
GHOST_PLAIN_MAX = 128 << 10     # largest unpacked ghost (v5.42; largest real: 26 KB)
MAX_BODY = 1 << 20              # largest request body read; larger gets 413 (largest sync seen: 42 KB)
SYNC_MAX_BODY = 8 << 20         # v5.40: POST /CC_Sync.php may be larger (iOS, #299); unpacked still <= 4 MB
TIMEOUT_S = 30                  # a connection idle this long is closed
REQUEST_S = 60                  # a request (headers and body) must arrive within this (v5.10, #143 8.5)
MAX_CONNECTIONS = 256           # connections handled at once; more are closed (v5.10; v5.83: was 64)
LOCAL_CONNECTIONS = 64          # v5.81 (#248): own slots for connections from this machine (Caddy)
KEEPALIVE_S = 2                 # v5.83 (#248): idle wait for a connection's next request; 0 = close after each
LISTEN_QUEUE = 512              # v5.83 (#248): the listen backlog (Python's default was 5)
PER_IP = 0                      # v5.83 (#248): phone connections one IP may hold at once; 0 = no cap
STATS_S = 60                    # v5.83 (#248): the "slots:" log line, once a minute
SLOW_MS = 1000                  # v5.83 (#248): a request taking this long gets its own "slow:" line
SLOT_TTL = 24 * 3600            # an upload key unused this long is dropped (seconds)
SLOTS_PER_PLAYER = 2            # open upload keys per player; a new one drops the oldest (v5.12)
SLOTS_MAX = 256                 # open upload keys in all (at most SLOTS_MAX x GHOST_MAX on disk)
NO_CAR = 0xFFFFFFFF             # 10476 field 3 when any car will do (-1)


def read_string(payload, i):
    """u32 length + bytes at i; returns the text and the next offset."""
    n = struct.unpack_from("<I", payload, i)[0]
    return payload[i + 4:i + 4 + n].decode("ascii", "replace"), i + 4 + n


GHOST_REC = 0x90                # ghost record before the data (analysis/ghost-files.md 1.2)
GHOST_STEP_MS = 208             # one sample per 208 ms in every real ghost
GHOST_SAMPLES_MAX = 3000        # the game's sample arrays hold 3000 (analysis/ghost-files.md 2)
GHOST_NODES_MAX = 10000         # track node count K (largest real: 1704)


def validate_ghost(body, event=None, car=None, lap_ms=None):
    """v5.42 (issue #357, analysis/ghost-files.md 4): check a ghost file as
    the phone PUTs it. Returns (info, None) with info = dict(event, car,
    lap_ms, samples, nodes), or (None, reason). With event, car and lap_ms
    (the 10694 link), the record must match them."""
    try:
        plain, modes = blob.unwrap(body, GHOST_PLAIN_MAX)
    except (ValueError, zlib.error) as e:
        return None, f"blob: {e}"
    if modes != [1]:
        return None, f"blob modes {modes}, want [1]"
    if len(plain) < GHOST_REC:
        return None, "record too short"
    ev, car_, lap, n = (struct.unpack_from("<I", plain, o)[0] for o in (0x48, 0x58, 0x60, 0x8c))
    if len(plain) != GHOST_REC + n + 4:
        return None, f"size {len(plain)} != record + data {n} + 4"
    data = plain[GHOST_REC:GHOST_REC + n]
    if n < 18:
        return None, "data too short"
    version, count, flags = struct.unpack_from("<IIH", data)
    if version != 20 or flags != 0:
        return None, f"data version {version} flags {flags}"
    if not 1 <= count <= min(GHOST_SAMPLES_MAX, lap // GHOST_STEP_MS + 50):
        return None, f"{count} samples for a {lap} ms lap"
    end = 10 + 20 * count
    if end + 8 > n:
        return None, "data too short for its samples"
    nodes, sixteen = struct.unpack_from("<II", data, end)
    if not 1 <= nodes <= GHOST_NODES_MAX or sixteen != 16 or n != end + 8 + 4 * nodes:
        return None, f"node block (K {nodes}, {sixteen}) does not fit data size {n}"
    times = [struct.unpack_from("<I", data, 10 + 20 * i + 14)[0] for i in range(count)]
    if times[0] != 0 or any(b < a for a, b in zip(times, times[1:])):
        return None, "sample times not rising from 0"
    if times[-1] * 2 >= lap * 3:
        return None, f"last sample {times[-1]} ms >= 1.5 x lap {lap} ms"
    for want, got, what in ((event, ev, "event"), (car, car_, "car"), (lap_ms, lap, "lap")):
        if want is not None and want != got:
            return None, f"{what} {got} in the file, {want} in the link"
    return dict(event=ev, car=car_, lap_ms=lap, samples=count, nodes=nodes), None


GHOST_SPEED_OVER = 1.10        # v5.86 (#606 T5): a ghost this much faster than the event's median is logged
GHOST_PATH_SHORT = 0.90         # v5.86 (#606 T5): a path this much shorter than the event's median is logged
GHOST_SPEED_MIN = 3             # v5.86: other ghosts with a path needed on the event to compare


def ghost_path(body):
    """v5.86 (#606 T5): the length of a ghost's driven line, the sum of the
    distances between its x/y samples (game units, not calibrated), or None
    when the file can't be read (analysis/ghost-files.md 1.2)."""
    try:
        plain, _modes = blob.unwrap(body, GHOST_PLAIN_MAX)
        n = struct.unpack_from("<I", plain, 0x8c)[0]
        data = plain[GHOST_REC:GHOST_REC + n]
        count = struct.unpack_from("<I", data, 4)[0]
        pts = [struct.unpack_from("<ff", data, 10 + 20 * i) for i in range(count)]
    except (ValueError, zlib.error, struct.error):
        return None
    if len(pts) < 2 or not all(math.isfinite(x) and math.isfinite(y) for x, y in pts):
        return None
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


class Ghosts:
    """Time Trial ghost files (issue #94, analysis/leaderboard-ghosts.md).

    Files in DIR: <member>_<event>.bin (the fastest ghost of that member on
    that event, exactly as the phone sent it), upload_<key>.bin (PUT, not
    linked yet), index.json {"slots": {"<key>": {"player": .., "member": ..,
    "time": .., "put": bool}}, "ghosts": {"<member>_<event>": {"lap_ms": ..,
    "car": .., "ghost_id": .., "date": ..}}}. events: as in Times. cars:
    the game's car ids (--cars, v5.45), None = any."""

    def __init__(self, folder, url, events=None, cars=None):
        self.dir, self.url, self.events, self.cars = folder, url, events, cars
        os.makedirs(folder, exist_ok=True)
        self.index_path = os.path.join(folder, "index.json")
        try:
            d = json.load(open(self.index_path))
        except FileNotFoundError:
            d = {}
        self.slots, self.ghosts = d.get("slots", {}), d.get("ghosts", {})
        self.check_stored()

    def check_stored(self):
        """v5.42: every stored ghost is validated against its index entry;
        a failing one moves to rejected/ and leaves the index."""
        bad = []
        for name, g in list(self.ghosts.items()):
            path = os.path.join(self.dir, name + ".bin")
            try:
                with open(path, "rb") as f:
                    body = f.read()
            except FileNotFoundError:
                continue
            event = int(name.rsplit("_", 1)[1]) if name.rsplit("_", 1)[-1].isdigit() else None
            why = self.car_problem(g.get("car"))   # v5.45
            if not why:
                _, why = validate_ghost(body, event, g.get("car"), g.get("lap_ms"))
            if why:
                os.makedirs(os.path.join(self.dir, "rejected"), exist_ok=True)
                os.replace(path, os.path.join(self.dir, "rejected", name + ".bin"))
                del self.ghosts[name]
                bad.append(name)
                print(f"ghost {name} rejected: {why}", flush=True)
        if bad:
            self.save()
        return bad

    def save(self):
        tmp = self.index_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"slots": self.slots, "ghosts": self.ghosts}, f, indent=1, sort_keys=True)
        os.replace(tmp, self.index_path)

    def upload_path(self, key):
        return os.path.join(self.dir, f"upload_{key}.bin")

    def path_of(self, name):
        """The stored ghost's path length (index "path", computed and kept
        on first use), or None."""
        g = self.ghosts.get(name)
        if g is None:
            return None
        if "path" not in g:
            try:
                with open(os.path.join(self.dir, name + ".bin"), "rb") as f:
                    p = ghost_path(f.read())
            except OSError:
                p = None
            g["path"] = round(p, 1) if p is not None else None
        return g["path"]

    def speed_note(self, name, event, lap_ms):
        """v5.86 (#606 T5, log only): compare the ghost just kept with the
        event's other ghosts: " (ghost speed +N% over the event's median of
        K)" when its path / lap is more than GHOST_SPEED_OVER x their median,
        " (ghost path N% shorter ...)" when its path is under
        GHOST_PATH_SHORT x theirs; "" otherwise or with too few ghosts.
        Also logged on its own line, "ghost speed member M event E: ..."."""
        path = self.path_of(name)
        if not path or not lap_ms:
            return ""
        others = [(self.path_of(k), g["lap_ms"]) for k, g in list(self.ghosts.items())
                  if k != name and k.endswith(f"_{event}") and g.get("lap_ms")]
        others = [(p, t) for p, t in others if p]
        if len(others) < GHOST_SPEED_MIN:
            return ""
        speed = statistics.median(p / t for p, t in others)
        plen = statistics.median(p for p, _t in others)
        notes = []
        if path / lap_ms > GHOST_SPEED_OVER * speed:
            notes.append(f"ghost speed +{100 * (path / lap_ms / speed - 1):.0f}% over the event's median of {len(others)}")
        if path < GHOST_PATH_SHORT * plen:
            notes.append(f"ghost path {100 * (1 - path / plen):.0f}% shorter than the event's median of {len(others)}")
        if not notes:
            return ""
        print(f"ghost speed member {name.split('_')[0]} event {event}: {'; '.join(notes)}", flush=True)
        return " (" + "; ".join(notes) + ")"

    def forget(self, member, event, lap_ms):
        """v5.84 (#606): drop member's stored ghost on event if its lap is
        lap_ms (a rejected held time). Saves when one goes."""
        name = f"{member}_{event}"
        g = self.ghosts.get(name)
        if not g or g.get("lap_ms") != lap_ms:
            return False
        del self.ghosts[name]
        try:
            os.remove(os.path.join(self.dir, name + ".bin"))
        except FileNotFoundError:
            pass
        self.save()
        return True

    def drop(self, key):
        if self.slots.pop(key, None) is None:     # only keys we handed out name a file
            return
        try:
            os.remove(self.upload_path(key))
        except FileNotFoundError:
            pass

    def new_slot(self, player, member, host, build=None):
        """10695: a one-use key and the URL the phone PUTs the file to."""
        now = int(time.time())
        for k in [k for k, v in self.slots.items() if now - v["time"] > SLOT_TTL]:
            self.drop(k)
        # v5.12: oldest first, at most SLOTS_PER_PLAYER per player and SLOTS_MAX in all
        mine = sorted((v["time"], k) for k, v in self.slots.items() if v["player"] == player)
        for _t, k in mine[:max(0, len(mine) - SLOTS_PER_PLAYER + 1)]:
            self.drop(k)
        every = sorted((v["time"], k) for k, v in self.slots.items())
        for _t, k in every[:max(0, len(every) - SLOTS_MAX + 1)]:
            self.drop(k)
        key = secrets.token_hex(16)
        # time with fractions (v5.12): keys made in the same second still keep their order
        self.slots[key] = dict(player=player, member=member, build=build,
                               time=time.time(), put=False)
        self.save()
        base = self.url or f"http://{host}"
        return key, f"{base.rstrip('/')}/ghost/{key}"

    def put(self, key, body, build_policy=None):
        """HTTP PUT /ghost/<key>: keep the file until 10694 links it.
        Returns the HTTP status."""
        slot = self.slots.get(key)
        if slot is None or slot["put"]:
            return 404
        if build_policy and not build_policy.allows(slot.get("build")):
            return 403
        if not body or len(body) > GHOST_MAX:
            return 413
        _, why = validate_ghost(body)
        if why:
            print(f"ghost {key[:8]} PUT rejected: {why}", flush=True)
            return 400
        with open(self.upload_path(key), "wb") as f:
            f.write(body)
        slot["put"] = True
        self.save()
        return 200

    def car_problem(self, car):
        """v5.45 (issue #143 item 5): why a ghost's car must not be kept."""
        if self.cars is not None and car not in self.cars:
            return f"car {car} not in the car list"
        return None

    def link(self, payload, player):
        """10694: event, key, ghost id, lap ms, value, car, 4 floats. Keeps
        the file if it is the player's fastest on the event. Returns the
        reply status (1 if the key was known and uploaded by this player,
        else 0) and a line for the log. v5.84: last_kept = (member, event,
        lap ms) of a file kept by this call, else None."""
        self.last_kept = None
        event = struct.unpack_from("<I", payload)[0]
        key, i = read_string(payload, 4)
        ghost_id, i = read_string(payload, i)
        lap_ms, _value, car = struct.unpack_from("<III", payload, i)
        slot = self.slots.get(key)
        if slot is None or not slot["put"] or slot["player"] != player:
            self.drop(key)
            self.save()
            return 0, f"ghost {key[:8]} unknown"
        if event in IGNORED_EVENTS:         # accepted, not kept
            self.drop(key)
            self.save()
            return 1, f"ghost event {event} dropped (Race Selector)"
        if self.events is not None and event not in self.events:
            self.drop(key)
            self.save()
            return 1, f"ghost event {event} dropped (not in --events)"
        why = self.car_problem(car)         # v5.45
        if not why:
            with open(self.upload_path(key), "rb") as f:
                _, why = validate_ghost(f.read(), event, car, lap_ms)
        if why:                             # v5.42: the file must match the link
            self.drop(key)
            self.save()
            return 1, f"ghost {key[:8]} dropped: {why}"
        name = f"{slot['member']}_{event}"
        old = self.ghosts.get(name)
        if old is None or lap_ms <= old["lap_ms"]:
            os.replace(self.upload_path(key), os.path.join(self.dir, name + ".bin"))
            self.ghosts[name] = dict(lap_ms=lap_ms, car=car, ghost_id=ghost_id,
                                     date=datetime.date.today().isoformat())
            info = f"ghost event {event} {lap_ms} ms kept"
            self.last_kept = (slot["member"], event, lap_ms)
            info += self.speed_note(name, event, lap_ms)            # v5.86 (#606 T5), log only
        else:
            info = f"ghost event {event} {lap_ms} ms slower than {old['lap_ms']} ms"
        self.drop(key)
        self.save()
        return 1, info

    def find(self, member, event, car):
        """10476: the stored ghost file of member on event, or None. A
        given car (Watch Replay) must match the stored ghost's car."""
        g = None if event in IGNORED_EVENTS else self.ghosts.get(f"{member}_{event}")
        if g is None or (car != NO_CAR and car != g["car"]):
            return None
        try:
            with open(os.path.join(self.dir, f"{member}_{event}.bin"), "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None


def ghost_reply(payload, member, times, ghosts):
    """10476 reply: u32 status (0 none, 1 file inline), owner strings S1,
    S2, S3, skipped block, S4, S5 (as the start of a 10477 row), livery
    block (empty), u32 size + ghost file."""
    want, event, car = struct.unpack_from("<III", payload)
    if want == 0:                           # 0 = "myself" in ReplayCache
        want = member
    owner = times.by_member.get(want, "")
    if owner and times.hidden(owner, times.by_member.get(member, ""), friends_ok=True, event=event):
        return blob.u32(0), f"ghost of {want} on {event}: none (hidden)"
    data = ghosts.find(want, event, car)
    if data is None:
        return blob.u32(0), f"ghost of {want} on {event}: none"
    key = times.by_member.get(want, "")
    name = times.display_name(key) if key else ""
    out = (blob.u32(1) + blob.string(name) + blob.string("") + blob.string("") + blob.u32(0)
           + blob.string("") + blob.string(times.tag) + blob.u32(0) + blob.u32(len(data)) + data)
    return out, f"ghost of {want} on {event}: sent {len(data)} bytes"


# Cloud save, phase (a): backups only (v5.63, issue #501, analysis/cloud-save.md 2.1, 2.2, 2.4, 5).
SAVE_MAX = 9 << 20              # largest save PUT accepted (--cloud-save-max-bytes; character.2.dat ~4.3 MB)
SAVE_VERSIONS = 3               # versions kept per member (--cloud-save-versions)
SAVE_SLOT_OK = 0                # 10660 reply status: 0 = go on and PUT (0x1ce8de4 cbz; v5.63 sent 1 = failure)
SAVE_LIST_EMPTY = b"\0" * 12    # 47 reply: u32 A 0, B 0 (B != 1: ok, no saves), N 0 (v5.64)
SAVE_CORRUPT_KEEP = 3           # corrupt-save reports (22) kept per member, apart from the versions
SAVE_SLOT_TTL = 3600            # a save upload key unused this long is dropped (seconds)
SAVE_SLOTS_PER_MEMBER = 2       # open save upload keys per member; a new one drops the oldest
SAVE_SLOTS_MAX = 64             # open save upload keys in all
SAVE_NAME_RE = re.compile(r"\d{8}T\d{6}\d{6}Z-[0-9a-f]{32}\.bin")
SAVE_RESTORE_TTL = 3600         # a restore (GET) key unused this long is dropped (seconds; v5.65)
SAVE_RESTORES_PER_MEMBER = 2    # open restore keys per member; a new one drops the oldest (v5.65)
SAVE_RESTORES_MAX = 64          # open restore keys in all (v5.65)
# v5.70 (#514): what a healthy upload holds (analysis/cloud-save.md 2.6, 8.1)
SAVE_BUNDLE_FILES = ("character.2.dat", "player_profile.2.dat", "nrc.bin.2.dat")
SAVE_DAT_KEY = bytes.fromhex(   # the saves' XOR key (tools/rr3_dat.py KEY), to read character.2.dat's header
    "6495e450cfd20c325482fc438013a15e0b465cd7c687a8a955a794101133e767"
    "b0c9efda21113d918d884cc9fa815d9f171cda974b9cac92607fff3c40c65000")
SAVE_DAT_MAGIC = 0xABCFFCBA
SAVE_DAT_VERSION = 5


def xor_fold(data):
    """XOR of every byte of data, fast (big-int folding; no Python loop per byte)."""
    n = len(data)
    if n == 0:
        return 0
    x = int.from_bytes(data, "little")
    while n > 1:
        half = (n + 1) // 2
        x = (x & ((1 << (8 * half)) - 1)) ^ (x >> (8 * half))
        n = half
    return x & 0xFF


def dat_check(enc):
    """A character.2.dat as the game writes it (encrypted): magic, version 5,
    its size field equal to its length, and the last byte equal to the XOR
    of every decrypted byte before it (the game ignores a save otherwise;
    docs/details/save-file-details.md 2, 6). -> None, or why not."""
    n = len(enc)
    if n < 21:
        return f"character.2.dat too short ({n} bytes)"
    head = bytes(a ^ b for a, b in zip(enc[:12], SAVE_DAT_KEY))
    magic, version, size = struct.unpack(">III", head)
    if magic != SAVE_DAT_MAGIC or version != SAVE_DAT_VERSION:
        return f"character.2.dat header {magic:#x} version {version}"
    if size != n:
        return f"character.2.dat size field {size}, file {n} bytes"
    k = len(SAVE_DAT_KEY)
    full, rest = divmod(n - 1, k)          # the key bytes XORed into the first n - 1 bytes
    key_x = (xor_fold(SAVE_DAT_KEY) if full % 2 else 0) ^ xor_fold(SAVE_DAT_KEY[:rest])
    if xor_fold(enc[:-1]) ^ key_x != enc[-1] ^ SAVE_DAT_KEY[(n - 1) % k]:
        return "character.2.dat checksum byte wrong"
    return None


def save_check(body, name):
    """v5.70 (#514): may this stored version be offered and sent? The four
    checks of the spec: (1) md5 = the md5 in its name; (2) BinaryBlob mode 1
    with a valid checksum; (3) zlib unpacks completely to the declared size;
    (4) the bundle is u32 2, u32 3 and exactly the three save files, with a
    readable character.2.dat (dat_check). -> None, or why not (log only)."""
    m = SAVE_NAME_RE.fullmatch(name)
    if not m or hashlib.md5(body).hexdigest() != name[-36:-4]:
        return "md5 does not match the name"
    if len(body) < 12:
        return "too short"
    chk, mode, size = struct.unpack_from("<III", body)
    if mode != 1:
        return f"blob mode {mode}"
    if chk != blob.checksum(body[8:]):
        return "blob checksum wrong"
    try:
        z = zlib.decompressobj()
        plain = z.decompress(body[12:], size + 1)
        if not z.eof or z.unconsumed_tail or z.unused_data or len(plain) != size:
            return f"zlib: {len(plain)} bytes unpacked, {size} declared, stream {'ends' if z.eof else 'cut'}"
    except zlib.error as e:
        return f"zlib: {e}"
    try:
        ver, count = struct.unpack_from("<II", plain)
        if (ver, count) != (2, len(SAVE_BUNDLE_FILES)):
            return f"bundle header {ver}, {count}"
        i, files = 8, {}
        for _ in range(count):
            fname, i = read_string(plain, i)
            n = struct.unpack_from("<I", plain, i)[0]
            i += 4
            if i + n > len(plain):
                return f"bundle: {fname} runs past the end"
            files[fname], i = plain[i:i + n], i + n
        if i != len(plain):
            return f"bundle: {len(plain) - i} bytes after the last file"
        if sorted(files) != sorted(SAVE_BUNDLE_FILES):
            return f"bundle files {sorted(files)}"
    except (struct.error, IndexError, UnicodeDecodeError, ValueError) as e:
        return f"bundle not readable ({e.__class__.__name__})"
    return dat_check(files["character.2.dat"])


SAVE_PRESET_PICKS = 2           # v5.72 (#530, Tom: "twice a day"): preset picks per member per 24 h
SAVE_PRESET_WINDOW = 86400


def save_unbundle(body):
    """The files of a stored upload, {name: bytes} (call after save_check)."""
    plain = zlib.decompress(body[12:])
    i, files = 8, {}
    for _ in range(struct.unpack_from("<I", plain, 4)[0]):
        name, i = read_string(plain, i)
        n = struct.unpack_from("<I", plain, i)[0]
        files[name], i = plain[i + 4:i + 4 + n], i + 4 + n
    return files


def save_bundle(character, profile, nrc):
    """An upload as the game sends it: BinaryBlob mode 1 of u32 2, u32 3 and
    the three files in the game's order (analysis/cloud-save.md 2.6)."""
    files = (("character.2.dat", character), ("player_profile.2.dat", profile), ("nrc.bin.2.dat", nrc))
    plain = blob.u32(2, len(files)) + b"".join(blob.string(n) + blob.u32(len(d)) + d for n, d in files)
    return blob.wrap(plain, 1)


def load_presets(path):
    """--cloud-save-presets FILE (v5.72, #530): JSON {"presets": [{"id",
    "name", "file"}]}, file relative to the JSON's folder, a character.2.dat
    used as-is. A preset whose file is missing or that the game would ignore
    (dat_check) is left out and logged. -> [{"id", "name", "path"}]."""
    data = json.load(open(path))
    base, out, seen = os.path.dirname(os.path.abspath(path)), [], set()
    for p in data.get("presets", []):
        pid, name, file = str(p.get("id", "")), str(p.get("name", "")), str(p.get("file", ""))
        if not re.fullmatch(r"[a-z0-9_-]{1,32}", pid) or not name or pid in seen:
            print(f"[----] cloud save preset {pid!r}: needs a unique id (a-z 0-9 _ -) and a name; left out",
                  flush=True)
            continue
        full = os.path.join(base, file)
        try:
            why = dat_check(open(full, "rb").read())
        except OSError as e:
            why = f"not readable ({e.__class__.__name__})"
        if why:
            print(f"[----] cloud save preset {pid}: {full}: {why}; left out", flush=True)
            continue
        seen.add(pid)
        out.append({"id": pid, "name": name[:80], "path": full})
    return out


class MemberFile:
    """Member ids from a text file, one per line, # starts a comment; read
    again when the file changes (v5.65, --cloud-save-restore; the same
    format as --asset-testers). No file: nobody."""

    def __init__(self, path):
        self.path, self.ids, self.sig = path, set(), None

    def __contains__(self, member):
        try:
            st = os.stat(self.path) if self.path else None
        except OSError:
            st = None
        sig = (st.st_mtime_ns, st.st_size) if st else None
        if sig != self.sig:
            ids = set()
            if st:
                for line in open(self.path).read().splitlines():
                    line = line.split("#")[0].strip()
                    if line.isdigit():
                        ids.add(int(line))
            self.ids, self.sig = ids, sig
        return member in self.ids


def save_list_reply(save_id, upload_time, url):
    """47 reply with one save and one entry (v5.65, #514; analysis/
    cloud-save.md 2.3): A 0, B 1, N 1; name "save", M 1; flag 0, id, time,
    meta "" (row "Last Uploaded", no progress, no auto prompt), str "",
    u32 0 x3; tail: the download URL (one string per entry)."""
    return (blob.u32(0, 1, 1) + blob.string("save") + blob.u32(1)
            + blob.u32(0, save_id, upload_time) + blob.string("") + blob.string("") + blob.u32(0, 0, 0)
            + blob.string(url))
SAVE_PEEK_PLAIN = 64 << 10      # unpacked bytes read to name the subsyncs of a sync refused for size


def blob_note(body):
    """What a stored save looks like, without its content: the BinaryBlob
    mode and declared unpacked size, or why it is not a blob (log only)."""
    if len(body) < 8:
        return "not a blob (too short)"
    chk, mode = struct.unpack_from("<II", body)
    if chk != blob.checksum(body[8:]):
        return "not a blob (checksum)"
    if mode == 1 and len(body) >= 12:
        return f"blob mode 1, unpacks to {struct.unpack_from('<I', body, 8)[0]} bytes"
    return f"blob mode {mode}"


def peek_subsync_types(body, plain_max=SAVE_PEEK_PLAIN):
    """v5.63: the subsync types whose headers lie in the first plain_max
    unpacked bytes of a sync blob.unwrap() refused (log only: is it a
    corrupt-save report 22?). No checksum check; [] when unreadable."""
    try:
        d = body
        if len(d) >= 9 and struct.unpack_from("<I", d, 4)[0] == 2:
            k, out = d[8], bytearray()
            for b in d[9:9 + 12 + 4 * plain_max]:
                out.append(b ^ k)
                k = (k + 3) & 0xFF
            d = bytes(out)
        if len(d) < 12 or struct.unpack_from("<I", d, 4)[0] != 1:
            return []
        plain = zlib.decompressobj().decompress(d[12:], plain_max)
        i = blob.header(plain)["end"] + 4
        types = []
        while i + 16 <= len(plain):
            t, _t2, _z, n = struct.unpack_from("<IIII", plain, i)
            types.append(t)
            i += 16 + n
        return types
    except Exception:
        return []


def fsync_dir(path):
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


class CloudSaves:
    """Cloud save backups, phase (a) of issue #501: the game asks for an
    upload slot (10660), PUTs its save (BinaryBlob mode 1, as received) to
    the URL in the reply (<--ghost-url or http://Host>/save/<key>), then
    says it is done (10661). Corrupt-save reports (22) carry the save inline.

    Files in DIR, by member id only (never a phone id):
      <member>/<UTC time>-<md5>.bin          the newest `versions` uploads
      <member>/corrupt/<UTC time>-<md5>.bin  the newest SAVE_CORRUPT_KEEP reports
      slots.json                             open upload keys; v5.65: open restore keys
      pins.json                              v5.65: {"<member>": "<file>"}, the version
                                             the member's last restore came from
    Every file is written to a temporary name, fsynced and renamed; an old
    version is deleted only after the new one is in place. Lists (47) get
    an empty list (v5.64), except, since v5.65 (#514, phase (b)), for the
    members in `restore` (--cloud-save-restore): one row offering their
    newest version with a one-use GET /save/<key> URL. The version a GET
    sent in full is pinned: never rotated out, not counted in `versions`;
    the next restore moves the pin. Downloads by 48 are never answered."""

    def __init__(self, folder, url, max_bytes=SAVE_MAX, versions=SAVE_VERSIONS, restore=None, presets=None,
                 restore_all=False):
        self.dir, self.url, self.max_bytes, self.versions = folder, url, max_bytes, versions
        self.restore = restore              # v5.65: MemberFile of --cloud-save-restore, or None
        self.check_cache = {}               # v5.70: path -> ((size, mtime), save_check result)
        self.lock = threading.Lock()        # slots and files; the PUT runs outside the server lock
        os.makedirs(folder, exist_ok=True)
        self.slots_path = os.path.join(folder, "slots.json")
        self.pins_path = os.path.join(folder, "pins.json")
        try:
            data = json.load(open(self.slots_path))
        except FileNotFoundError:
            data = {}
        self.slots, self.restores = data.get("slots", {}), data.get("restores", {})
        try:
            self.pins = json.load(open(self.pins_path))
        except FileNotFoundError:
            self.pins = {}
        self.presets = presets or []        # v5.72 (#530): load_presets()
        self.restore_all = restore_all      # v5.73: --cloud-save-restore-all
        self.site_path = os.path.join(folder, "site.json")
        try:
            self.site = json.load(open(self.site_path)).get("members", {})
        except FileNotFoundError:
            self.site = {}

    def save_slots(self):
        tmp = self.slots_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"slots": self.slots, "restores": self.restores}, f, indent=1, sort_keys=True)
        os.replace(tmp, self.slots_path)

    def save_pins(self):
        tmp = self.pins_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.pins, f, indent=1, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.pins_path)
        fsync_dir(self.dir)

    def pinned(self, member):
        return self.pins.get(str(int(member)))

    def site_member(self, member):
        """v5.72 (#530): the member's site state: optin (restores from the
        site), base (their last own upload before a preset, kept like a pin),
        on_preset, picks (times of preset picks), presets {file: preset id}."""
        return self.site.get(str(int(member)), {})

    def save_site(self):
        tmp = self.site_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"members": self.site}, f, indent=1, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.site_path)
        fsync_dir(self.dir)

    def may_restore(self, member, build=None):
        """Restores (a real 47 row) for the tester file (--cloud-save-restore),
        since v5.72 members who opted in on the site, and since v5.73 with
        --cloud-save-restore-all every member whose sync isn't from an iOS
        build (Tom 2026-11-09: "Android only for now")."""
        if (self.restore and member in self.restore) or self.site_member(member).get("optin"):
            return True
        return bool(self.restore_all and not (build and IOS_BUILD_RE.match(build)))

    def trim(self, member):
        """Delete the oldest versions beyond `versions`; the pinned one is
        kept and not counted (v5.65). -> versions kept. Call with self.lock held."""
        folder = self.member_dir(member)
        keep = {self.pinned(member), self.site_member(member).get("base")}     # v5.72: and the base
        rolling = [n for n in self.stored(folder) if n not in keep]
        for n in rolling[:max(0, len(rolling) - self.versions)]:
            os.remove(os.path.join(folder, n))
        return min(len(rolling), self.versions)

    def new_slot(self, member, host, build=None):
        """10660: a one-use key and the URL the phone PUTs the save to."""
        now = time.time()
        with self.lock:
            for k in [k for k, v in self.slots.items() if now - v["time"] > SAVE_SLOT_TTL]:
                del self.slots[k]
            mine = sorted((v["time"], k) for k, v in self.slots.items() if v["member"] == member)
            for _t, k in mine[:max(0, len(mine) - SAVE_SLOTS_PER_MEMBER + 1)]:
                del self.slots[k]
            every = sorted((v["time"], k) for k, v in self.slots.items())
            for _t, k in every[:max(0, len(every) - SAVE_SLOTS_MAX + 1)]:
                del self.slots[k]
            key = secrets.token_hex(16)
            self.slots[key] = dict(member=member, build=build, time=now, put=False)
            self.save_slots()
        base = self.url or f"http://{host}"
        return key, f"{base.rstrip('/')}/save/{key}"

    def slot_member(self, key):
        with self.lock:
            return (self.slots.get(key) or {}).get("member")

    def member_dir(self, member, corrupt=False):
        path = os.path.join(self.dir, str(int(member)))
        return os.path.join(path, "corrupt") if corrupt else path

    @staticmethod
    def stored(folder):
        """Stored files of a folder, oldest first (names start with the UTC time)."""
        try:
            return sorted(n for n in os.listdir(folder) if SAVE_NAME_RE.fullmatch(n))
        except FileNotFoundError:
            return []

    def store(self, member, body, corrupt=False):
        """Keep body for member. -> (stored: bool, md5, count kept). Same md5
        as the newest file: not stored again. Call with self.lock held."""
        folder = self.member_dir(member, corrupt)
        keep = SAVE_CORRUPT_KEEP if corrupt else self.versions
        md5 = hashlib.md5(body).hexdigest()
        old = self.stored(folder)
        if old and old[-1].endswith(f"-{md5}.bin"):
            return False, md5, len(old)
        os.makedirs(folder, exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        name = f"{stamp}-{md5}.bin"
        tmp = os.path.join(folder, f".{name}.tmp")
        try:
            with open(tmp, "wb") as f:
                f.write(body)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, os.path.join(folder, name))
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        fsync_dir(folder)
        if not corrupt:                             # v5.65: the pinned version is skipped
            return True, md5, self.trim(member)
        now = self.stored(folder)
        for n in now[:max(0, len(now) - keep)]:     # only once the new one is in place
            os.remove(os.path.join(folder, n))
        return True, md5, min(len(now), keep)

    def put(self, key, body, build_policy=None):
        """HTTP PUT /save/<key>. -> (HTTP status, log text). Never logs content."""
        with self.lock:
            slot = self.slots.get(key)
            if slot is None or slot["put"]:
                return 404, "unknown key"
            member = slot["member"]
            if build_policy and not build_policy.allows(slot.get("build")):
                return 403, f"member {member}: build {slot.get('build') or 'unknown'} not allowed"
            if not body or len(body) > self.max_bytes:
                return 413, f"member {member}: {len(body)} bytes, over the limit {self.max_bytes}"
            slot["put"] = True              # one use, even if storing fails below
            self.save_slots()
            try:
                new, md5, n = self.store(member, body)
            except OSError as e:
                return 500, f"member {member}: not stored ({e.__class__.__name__})"
        return 200, (f"member {member}: {len(body)} bytes md5 {md5} ({blob_note(body)}): "
                     + ("stored" if new else "same as newest") + f", {n} version(s)")

    def done(self, payload):
        """10661: the payload starts with the slot key; the rest is only
        measured. Drops the key. -> log text."""
        try:
            key, i = read_string(payload, 0)
        except (struct.error, IndexError):
            return f"save upload done: not read ({len(payload)} bytes)"
        with self.lock:
            slot = self.slots.pop(key, None)
            if slot is not None:
                self.save_slots()
        state = "unknown key" if slot is None else "uploaded" if slot["put"] else "never uploaded"
        return f"save upload done: key {key[:8]} {state}; {len(payload) - i} more bytes"

    def list_reply(self, member, host, build=None):
        """47 (v5.65, #514): for a member in --cloud-save-restore with a
        stored version, one row offering the newest and a one-use key for
        GET /save/<key>. -> (reply, log text); reply None = the empty list."""
        if not self.may_restore(member, build):
            return None, "save list: empty" + (" (iOS: not for everyone yet)" if self.restore_all and build
                                               and IOS_BUILD_RE.match(build) else "")
        now = time.time()
        skipped = []
        with self.lock:
            folder = self.member_dir(member)
            names = self.stored(folder)
            if not names:
                return None, "save list: empty (no version stored)"
            name = None
            for n in reversed(names):           # v5.70: the newest version that passes save_check
                why = self.checked(folder, n)
                if why is None:
                    name = n
                    break
                skipped.append(f"{n[:22]}: {why}")
                print(f"[----] save check failed: member {member}: {n}: {why}", flush=True)
            if name is None:
                return None, f"save list: empty (no version passes the checks: {'; '.join(skipped)})"
            for k in [k for k, v in self.restores.items() if now - v["time"] > SAVE_RESTORE_TTL]:
                del self.restores[k]
            mine = sorted((v["time"], k) for k, v in self.restores.items() if v["member"] == member)
            for _t, k in mine[:max(0, len(mine) - SAVE_RESTORES_PER_MEMBER + 1)]:
                del self.restores[k]
            every = sorted((v["time"], k) for k, v in self.restores.items())
            for _t, k in every[:max(0, len(every) - SAVE_RESTORES_MAX + 1)]:
                del self.restores[k]
            key = secrets.token_hex(16)
            self.restores[key] = dict(member=member, file=name, build=build, time=now)
            self.save_slots()
        uploaded = int(datetime.datetime.strptime(name[:15], "%Y%m%dT%H%M%S")
                       .replace(tzinfo=datetime.timezone.utc).timestamp())
        md5 = name.split("-")[1][:32]
        base = self.url or f"http://{host}"
        reply = save_list_reply(int(md5[:8], 16), uploaded, f"{base.rstrip('/')}/save/{key}")
        return reply, (f"save list: {name[:22]} md5 {md5[:8]}, restore key {key[:8]}"
                       + (f" (skipped {len(skipped)} failing the checks)" if skipped else ""))

    def checked(self, folder, name):
        """save_check of a stored file, remembered by (size, mtime) so a 47
        doesn't unpack every version again. Call with self.lock held. -> None
        or why not."""
        path = os.path.join(folder, name)
        try:
            st = os.stat(path)
        except OSError:
            return "file is gone"
        sig = (st.st_size, st.st_mtime_ns)
        hit = self.check_cache.get(path)
        if hit and hit[0] == sig:
            return hit[1]
        try:
            why = save_check(open(path, "rb").read(), name)
        except OSError as e:
            why = f"not readable ({e.__class__.__name__})"
        self.check_cache[path] = (sig, why)
        return why

    def restore_member(self, key):
        with self.lock:
            return (self.restores.get(key) or {}).get("member")

    def get(self, key, build_policy=None):
        """HTTP GET /save/<key> (v5.65): the stored version, unchanged. The
        key is used up here, whatever happens next. -> (HTTP status, body or
        None, log text, (member, file) to pin once the body is sent, or None)."""
        with self.lock:
            r = self.restores.pop(key, None)
            if r is None:
                return 404, None, "unknown key", None
            self.save_slots()
            member, name = r["member"], r["file"]
            if build_policy and not build_policy.allows(r.get("build")):
                return 403, None, f"member {member}: build {r.get('build') or 'unknown'} not allowed", None
            try:
                body = open(os.path.join(self.member_dir(member), name), "rb").read()
            except OSError:
                return 404, None, f"member {member}: {name} is gone", None
        why = save_check(body, name)            # v5.70: the bytes about to be sent, checked again
        if why is not None:
            print(f"[----] save check failed: member {member}: {name}: {why}", flush=True)
            return 404, None, f"member {member}: {name} fails the checks ({why}), not sent", None
        md5 = hashlib.md5(body).hexdigest()
        return 200, body, f"member {member}: {name}, {len(body)} bytes md5 {md5}", (member, name)

    def site_versions(self, member):
        """The member's stored versions for the site, newest first. Call with self.lock held."""
        sm, folder = self.site_member(member), self.member_dir(member)
        out = []
        for n in reversed(self.stored(folder)):
            kind = ("preset" if n in sm.get("presets", {}) else "own")
            out.append({"time": int(datetime.datetime.strptime(n[:15], "%Y%m%dT%H%M%S")
                                    .replace(tzinfo=datetime.timezone.utc).timestamp()),
                        "kind": kind, "preset": sm.get("presets", {}).get(n),
                        "base": n == sm.get("base"), "restored": n == self.pinned(member),
                        "ok": self.checked(folder, n) is None})
        return out

    def site_info(self, member, now):
        """GET /prr/api/me/cloudsave (v5.72, #530)."""
        with self.lock:
            sm = self.site_member(member)
            picks = [t for t in sm.get("picks", []) if now - t < SAVE_PRESET_WINDOW]
            versions = self.site_versions(member)
        return {"presets": [{"id": p["id"], "name": p["name"]} for p in self.presets],
                "optin": bool(sm.get("optin")), "tester": bool(self.restore and member in self.restore),
                "on_preset": bool(sm.get("on_preset")),
                "picks_left": max(0, SAVE_PRESET_PICKS - len(picks)),
                "next_pick": int(min(picks) + SAVE_PRESET_WINDOW) if len(picks) >= SAVE_PRESET_PICKS else None,
                "has_upload": any(v["kind"] == "own" and v["ok"] for v in versions),
                "has_base": bool(sm.get("base")), "versions": versions}

    def site_preset(self, member, pid, now):
        """POST /prr/api/me/cloudsave/preset {"id"} (v5.72, #530): the preset
        character.2.dat, unchanged, with the member's own player_profile.2.dat
        and nrc.bin.2.dat from their newest good upload, stored as their newest
        version; opts the member in. Their last own upload becomes the base
        (kept, not rotated out) unless they are already on a preset.
        -> (HTTP status, error or None, log text)."""
        preset = next((p for p in self.presets if p["id"] == pid), None)
        if preset is None:
            return 404, "no such save", f"preset {pid!r}: unknown"
        try:
            character = open(preset["path"], "rb").read()
        except OSError as e:
            return 503, "this save is not available right now", f"preset {pid}: {e.__class__.__name__}"
        with self.lock:
            sm = self.site.setdefault(str(int(member)), {})
            picks = [t for t in sm.get("picks", []) if now - t < SAVE_PRESET_WINDOW]
            if len(picks) >= SAVE_PRESET_PICKS:
                return 409, "you can pick a save twice a day", f"preset {pid}: limit ({len(picks)} in 24 h)"
            folder, presets_of = self.member_dir(member), sm.get("presets", {})
            good = [n for n in reversed(self.stored(folder)) if self.checked(folder, n) is None]
            own = [n for n in good if n not in presets_of]
            if not good:
                return 409, "no backup yet: in the game, Settings > Cloud Save > Backup To Cloud once", \
                    f"preset {pid}: no good upload"
            others = save_unbundle(open(os.path.join(folder, good[0]), "rb").read())
            body = save_bundle(character, others["player_profile.2.dat"], others["nrc.bin.2.dat"])
            why = save_check(body, f"20000101T000000000000Z-{hashlib.md5(body).hexdigest()}.bin")
            if why:
                return 500, "this save failed a check", f"preset {pid}: {why}"
            if not sm.get("on_preset") and own:
                sm["base"] = own[0]                 # before store(), so the rotation keeps it
            new, md5, kept = self.store(member, body)
            name = self.stored(folder)[-1]
            presets_of[name] = pid
            sm["presets"] = {n: v for n, v in presets_of.items() if os.path.exists(os.path.join(folder, n))}
            sm.update(optin=True, on_preset=True, picks=picks + [now])
            self.save_site()
        return 200, None, (f"preset {pid}: {'stored' if new else 'same as newest'} md5 {md5[:8]}, "
                           f"base {str(sm.get('base'))[:22]}, {kept} rolling")

    def site_own(self, member):
        """POST /prr/api/me/cloudsave/own (v5.72): the member's base (last own
        upload before a preset) becomes the newest version again; the base is
        then released. -> (HTTP status, error or None, log text)."""
        with self.lock:
            sm = self.site.get(str(int(member)))
            folder = self.member_dir(member)
            base = (sm or {}).get("base")
            if not base or self.checked(folder, base) is not None:
                return 409, "no own save kept to go back to", "own: no good base"
            new, md5, kept = self.store(member, open(os.path.join(folder, base), "rb").read())
            sm.update(on_preset=False, base=None)
            self.trim(member)
            self.save_site()
        return 200, None, f"own: {base[:22]} {'stored' if new else 'already newest'} md5 {md5[:8]}"

    def site_optout(self, member):
        """POST /prr/api/me/cloudsave/optout (v5.72): no more site restores
        (the files stay). -> (HTTP status, error or None, log text)."""
        with self.lock:
            sm = self.site.get(str(int(member)))
            if sm:
                sm["optin"] = False
                self.save_site()
        return 200, None, "optout"

    def pin(self, member, name):
        """Pin the version a restore sent in full (v5.65); the old pin, if
        any, rotates normally from now on. -> log text."""
        with self.lock:
            old = self.pinned(member)
            self.pins[str(int(member))] = name
            self.save_pins()
            kept = self.trim(member)
        return f"pinned {name[:22]}" + (f" (was {old[:22]})" if old and old != name else "") + f", {kept} rolling"

    def corrupt(self, member, payload):
        """22: corrupt-save report: u32 bool, u32 bool, u32 size + save,
        str, str, u32 0, str (analysis/cloud-save.md 2.1). Keeps the save
        under <member>/corrupt/. -> log text."""
        try:
            n = struct.unpack_from("<I", payload, 8)[0]
            if n == 0 or 12 + n > len(payload):
                raise ValueError(f"size {n} past the end")
            data = payload[12:12 + n]
        except (struct.error, ValueError) as e:
            return f"corrupt-save report not read ({len(payload)} bytes: {e})"
        if n > self.max_bytes:
            return f"corrupt-save report: {n} bytes, over the limit {self.max_bytes}, not stored"
        with self.lock:
            try:
                new, md5, kept = self.store(member, data, corrupt=True)
            except OSError as e:
                return f"corrupt-save report: not stored ({e.__class__.__name__})"
        return (f"corrupt-save report: {n} bytes md5 {md5} ({blob_note(data)}): "
                + ("stored" if new else "same as newest") + f", {kept} kept")


MAIL_MAX = 20                   # mails kept per player, newest first
MAIL_DAYS = 30                  # a mail older than this is dropped
MAIL_PER_RESULT = 20            # players one new best mails at most (v5.9, issue #143 8.1)


class Mail:
    """Mail "someone beat your time" (analysis/leaderboard-ghosts.md 7),
    kept in a JSON file: {"<player key>": [{"time": .., "event": ..,
    "sender": "<player key>", "lap_ms": .., "car": ..}]}, newest first;
    one mail per event (the latest)."""

    def __init__(self, path):
        self.path = path
        try:
            self.data = json.load(open(path)) if path else {}
        except FileNotFoundError:
            self.data = {}

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=1, sort_keys=True)
        os.replace(tmp, self.path)

    def add(self, to, event, sender, lap_ms, car, now=None, save=True):
        now = int(time.time()) if now is None else now
        box = [m for m in self.data.get(to, []) if now - m["time"] < MAIL_DAYS * 86400
               and m["event"] != event]     # one mail per event: the latest
        box.insert(0, dict(time=now, event=event, sender=sender, lap_ms=lap_ms, car=car))
        self.data[to] = box[:MAIL_MAX]
        if save:
            self.save()

    def since(self, key, t):
        return [m for m in self.data.get(key, []) if m["time"] > t]


def mail_reply(payload, key, times):
    """10459 reply (read by 0x1357200): u32 count, then per mail u32 0
    (dropped by the phone), u32 time, u32 event and a row read by 0xa71bf4:
    str name, u32 member id, str s2, str s3, u32 0 (skipped block), str
    s4, 7 u32, 4 f32 (meaning not traced; sent as 0), u32 bool 0. The
    request is u32 since (the phone's last check, [Character+0x1270])."""
    since = struct.unpack_from("<I", payload)[0] if len(payload) >= 4 else 0
    out = b""
    n = 0
    for m in times.mail.since(key, since) if times.mail else []:
        member = times.members.get(m["sender"])
        if not member or times.hidden(m["sender"], key, friends_ok=True):  # shadowed (v5.13) or banned (v5.80)
            continue
        out += (blob.u32(0, m["time"], m["event"]) + blob.string(times.display_name(m["sender"]))
                + blob.u32(member) + blob.string("") + blob.string("") + blob.u32(0) + blob.string("")
                + blob.u32(0, 0, 0, 0, 0, 0, 0) + struct.pack("<4f", 0, 0, 0, 0) + blob.u32(0))
        n += 1
    return blob.u32(n) + out, f"mail since {since}: sent {n}"


FRIENDS_EVENTS_MAX = 64          # events read from one 10419 request
# Friends and the website login (v5.16, issue #218; design: issue #163).
LOGIN_PERIOD_S = 60             # a login code changes every minute; one period each side is accepted
LOGIN_FAILS_MAX = 5             # wrong codes per player before LOGIN_LOCK_S
LOGIN_LOCK_S = 15 * 60
LOGIN_IP_FAILS_MAX = 20         # wrong codes per IP per hour
SESSION_S = 12 * 3600           # a website login lasts at most this (#163 Decided 1.6)
SESSIONS_PER_PLAYER = 10        # the oldest is ended when a player opens more
REQUESTS_PER_DAY = 20           # friend requests one player may send per day
FRIENDS_MAX = 100               # friends plus pending requests sent, per player
SEARCH_MAX = 20                 # usernames one search returns
# Friends' details, 10472 (v5.53, issue #278; analysis/social-login.md 9.2).
DETAILS_STATS = 26              # u32 stats in a 10472 request (v5.54: 26, analysis/social-login.md 9.9)
DETAILS_FRIENDS_AT = 24         # the reply inserts the friend count (+0xec) here: 24 + 1 + 2 = 27 stats
DETAILS_IDS_MAX = 64            # social ids per list read from a request (prr_social phones send 0)
DETAILS_ID_LEN_MAX = 128        # bytes per social id
DETAILS_CARS_MAX = 1024         # owned car ids kept per player (the game has about 300 cars)
DETAILS_LIST2_MAX = 4096        # ids kept from the request's second list (meaning not traced)


def login_code(secret_hex, member, period):
    """The code the phone puts in the login URL (#163 Decided 1.3): the
    first 16 bytes, as hex, of HMAC-SHA256(secret, b"login" + u32 member +
    u64 period), little-endian; period = Unix time // LOGIN_PERIOD_S."""
    msg = b"login" + struct.pack("<IQ", member, period)
    return hmac.new(bytes.fromhex(secret_hex), msg, hashlib.sha256).digest()[:16].hex()


def reset_request_ok(member, v):
    """A stored reset request (v5.54, #423) that can be used."""
    return (isinstance(member, str) and member.isdigit() and isinstance(v, dict)
            and isinstance(v.get("key"), str) and isinstance(v.get("secret"), str)
            and re.fullmatch(r"[0-9a-f]{64}", v["secret"]) is not None
            and isinstance(v.get("seen"), int) and isinstance(v.get("asked"), int)
            and isinstance(v.get("ip"), str))


class Friends:
    """Player secrets, friends and the website login (v5.16, issue #218).

    Files: --secrets {"<player key>": "<64 hex>"} (the first secret each
    player's phone sent; kept as sent, since the server must recompute the
    login code: private, mode 0600) and --friends {"friends": [[key a,
    key b, since]], "requests": [[from key, to key, time]]}. In memory
    only: sessions (a server restart logs everyone out; the next tap in
    the game logs back in), wrong-code counts, used codes and the
    requests sent today.

    v5.54 (#423): also in memory, the newest secret each phone sent that
    differs from the kept one (candidates); and in reset_requests_path
    (private) the reset requests filed by a wrong login code made with
    that newer secret: {"<member>": {"key", "secret", "seen", "asked",
    "ip"}}."""

    def __init__(self, secrets_path=None, friends_path=None, resets_path=None, details_path=None,
                 reset_requests_path=None):
        self.secrets_path, self.friends_path = secrets_path, friends_path
        self.resets_path = resets_path
        self.reset_requests_path = reset_requests_path
        try:
            d = json.load(open(reset_requests_path)) if reset_requests_path else {}
        except (FileNotFoundError, ValueError):
            d = {}
        self.reset_requests = {m: v for m, v in d.items() if reset_request_ok(m, v)}
        self.candidates = {}            # v5.54: player key -> (newer secret, first seen)
        self.differs_logged = set()     # v5.54: player keys logged as "secret differs" this run
        # v5.53 (#278): each player's own 10472 values, shown to their friends
        # {"<player key>": {"t": last 10472, "stats": [26] (v5.54), "cars": [..],
        # "cars0": u32, "list2": [..], "list2_0": u32}}
        self.details_path = details_path
        try:
            d = json.load(open(details_path)) if details_path else {}
        except (FileNotFoundError, ValueError):
            d = {}
        self.details = {k: v for k, v in d.items() if details_problem(v) is None}
        try:
            self.secrets = json.load(open(secrets_path)) if secrets_path else {}
        except FileNotFoundError:
            self.secrets = {}
        try:
            d = json.load(open(friends_path)) if friends_path else {}
        except FileNotFoundError:
            d = {}
        self.pairs = {frozenset(p[:2]): p[2] for p in d.get("friends", [])}
        self.requests = {(a, b): t for a, b, t in d.get("requests", [])}
        self.sessions = {}              # token -> (player key, created)
        self.fails = {}                 # player key -> [wrong-code times]
        self.ip_fails = {}              # IP -> [wrong-code times]
        self.used = {}                  # (member, code) -> time used
        self.sent = {}                  # player key -> [request times]

    @staticmethod
    def write(path, data, private=False):
        if not path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600 if private else 0o644)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        os.replace(tmp, path)

    def save(self):
        self.write(self.friends_path, dict(
            friends=sorted([*sorted(p), t] for p, t in self.pairs.items()),
            requests=sorted([a, b, t] for (a, b), t in self.requests.items())))

    def set_secret(self, key, secret):
        """Keep the first secret a player's phone sends; a different one
        later is ignored (#163 Decided 1.2). True when it is new."""
        if not secret or key == "unknown" or key in self.secrets:
            return False
        self.secrets[key] = secret
        self.write(self.secrets_path, self.secrets, private=True)
        return True

    def note_secret(self, key, secret, now=None):
        """v5.54 (#423 part 1): remember the newest secret a phone sends
        that differs from the kept one (in memory only; the kept one stays).
        Returns a note for the log the first time per player per run, else
        "". The kept secret sent again forgets the newer one."""
        if not secret or key == "unknown" or key not in self.secrets:
            return ""
        if secret == self.secrets[key]:
            self.candidates.pop(key, None)
            return ""
        now = time.time() if now is None else now
        old = self.candidates.get(key)
        if old is None or old[0] != secret:
            self.candidates[key] = (secret, int(now))
        if key in self.differs_logged:
            return ""
        self.differs_logged.add(key)
        return "secret differs from the kept one (kept the first)"

    def file_reset_request(self, key, member, ip, now):
        """v5.54 (#423 part 3): a wrong login code made with the phone's
        newer secret files (or renews) the member's reset request. One per
        member; a later one replaces it. An admin approves it with
        --secret-resets (apply_resets keeps this secret)."""
        secret, seen = self.candidates[key]
        self.reset_requests[str(member)] = dict(key=key, secret=secret, seen=seen, asked=int(now), ip=ip or "")
        self.write(self.reset_requests_path, self.reset_requests, private=True)

    def apply_resets(self, by_member):
        """Admin reset (v5.25, issue #163): --secret-resets lists member ids,
        one per line (# starts a comment). Each listed player's secret is
        dropped, their website sessions and wrong-code count end, and the
        file is emptied. The phone's next request then sends its secret
        again and the server keeps that one. v5.54 (#423 part 3): a member
        with an open reset request gets that request's secret kept at once
        instead (no race for "the next secret"). by_member = Times.by_member.
        Returns a line for the log, or "" when there was nothing to do."""
        path = self.resets_path
        try:
            if not path or os.path.getsize(path) == 0:
                return ""
            lines = open(path).read().splitlines()
            open(path, "w").close()
        except OSError:
            return ""
        done, bad = [], []
        for line in lines:
            line = line.split("#")[0].strip()
            if not line:
                continue
            key = by_member.get(int(line)) if line.isdigit() else None
            if key is None:
                bad.append(line)
                continue
            req = self.reset_requests.pop(line, None)
            if req and req["key"] == key:   # v5.54 (#423 part 3): keep the requested secret now
                self.secrets[key] = req["secret"]
                done.append(f"{line} (requested secret kept)")
            else:
                self.secrets.pop(key, None)
                done.append(line)
            self.candidates.pop(key, None)
            self.differs_logged.discard(key)
            self.end_sessions(key)
            self.fails.pop(key, None)
        if done:
            self.write(self.secrets_path, self.secrets, private=True)
            self.write(self.reset_requests_path, self.reset_requests, private=True)
        out = f"secret reset for member(s) {', '.join(done)}" if done else ""
        if bad:
            out += ("; " if out else "") + f"secret reset: unknown member(s) {', '.join(bad)}"
        return out

    # Login ------------------------------------------------------------
    @staticmethod
    def recent(times_list, now, window):
        return [t for t in times_list if now - t < window]

    def check_login(self, key, member, code, ip, now=None):
        """A login code from the URL. Returns (True, "") or (False, why)."""
        now = time.time() if now is None else now
        self.used = {k: t for k, t in self.used.items() if now - t < 4 * LOGIN_PERIOD_S}
        fails = self.recent(self.fails.get(key, []), now, LOGIN_LOCK_S)
        ip_fails = self.recent(self.ip_fails.get(ip, []), now, 3600)
        if len(fails) >= LOGIN_FAILS_MAX:
            return False, "locked"
        if ip and len(ip_fails) >= LOGIN_IP_FAILS_MAX:
            return False, "too many tries from this address"
        secret = self.secrets.get(key)
        code = code.lower()
        ok = secret and re.fullmatch(r"[0-9a-f]{32}", code) and any(
            hmac.compare_digest(login_code(secret, member, int(now // LOGIN_PERIOD_S) + d), code)
            for d in (-1, 0, 1))
        if ok and (member, code) not in self.used:
            self.used[(member, code)] = now
            self.fails.pop(key, None)
            return True, ""
        if ok:      # a right code sent again (a second tap in the same minute): v5.17 counts no failure
            return False, "used code"
        self.fails[key] = fails + [now]
        if ip:
            self.ip_fails[ip] = ip_fails + [now]
        cand = self.candidates.get(key) if secret else None
        if cand and re.fullmatch(r"[0-9a-f]{32}", code) and any(
                hmac.compare_digest(login_code(cand[0], member, int(now // LOGIN_PERIOD_S) + d), code)
                for d in (-1, 0, 1)):
            # v5.54 (#423): the phone's newer secret made this code; still a wrong code
            self.file_reset_request(key, member, ip, now)
            seen = datetime.datetime.fromtimestamp(cand[1], datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            return False, f"wrong code (phone's secret changed {seen}; reset requested)"
        return False, "no secret" if not secret else "wrong code"

    def new_session(self, key, now=None):
        now = time.time() if now is None else now
        self.expire(now)
        mine = sorted((c, t) for t, (k, c) in self.sessions.items() if k == key)
        for _c, t in mine[:max(0, len(mine) - SESSIONS_PER_PLAYER + 1)]:
            del self.sessions[t]
        token = secrets.token_hex(32)
        self.sessions[token] = (key, now)
        return token

    def expire(self, now):
        self.sessions = {t: v for t, v in self.sessions.items() if now - v[1] < SESSION_S}

    def session(self, token, now=None):
        """The player key of a session token, or None."""
        now = time.time() if now is None else now
        v = self.sessions.get(token or "")
        if v is None or now - v[1] >= SESSION_S:
            self.sessions.pop(token or "", None)
            return None
        return v[0]

    def end_sessions(self, key, token=None):
        """End one session (token) or all of a player's (token None)."""
        self.sessions = {t: v for t, v in self.sessions.items()
                         if not (v[0] == key and (token is None or t == token))}

    def set_details(self, key, d, now=None):
        """Keep a player's own 10472 values (v5.53). The file is written
        when the stats or lists change, so the time ("last seen") of an
        unchanged request is kept in memory only until the next change."""
        now = int(time.time() if now is None else now)
        old = self.details.get(key)
        new = dict(d, t=now)
        self.details[key] = new
        if old is None or {k: v for k, v in old.items() if k != "t"} != d:
            self.write(self.details_path, self.details)

    # Friends ------------------------------------------------------------
    def friends_of(self, key):
        return [k for p in self.pairs for k in p if key in p and k != key]

    def are_friends(self, a, b):
        return frozenset((a, b)) in self.pairs

    def act(self, action, me, other, now=None):
        """A friend action from the website. Returns None if done, else the
        reason it was refused."""
        now = time.time() if now is None else now
        if other == me:
            return "that is you"
        if action == "request":
            if self.are_friends(me, other):
                return "already friends"
            if (other, me) in self.requests:            # they asked first: accept
                return self.act("accept", me, other, now)
            if (me, other) in self.requests:
                return "already sent"
            if len(self.friends_of(me)) + sum(a == me for a, _ in self.requests) >= FRIENDS_MAX:
                return f"at most {FRIENDS_MAX} friends and requests"
            sent = self.recent(self.sent.get(me, []), now, 86400)
            if len(sent) >= REQUESTS_PER_DAY:
                return f"at most {REQUESTS_PER_DAY} requests a day"
            self.sent[me] = sent + [now]
            self.requests[(me, other)] = int(now)
        elif action == "accept":
            if self.requests.pop((other, me), None) is None:
                return "no such request"
            if len(self.friends_of(me)) >= FRIENDS_MAX:
                self.requests[(other, me)] = int(now)
                return f"at most {FRIENDS_MAX} friends"
            self.requests.pop((me, other), None)
            self.pairs[frozenset((me, other))] = int(now)
        elif action == "reject":
            if self.requests.pop((other, me), None) is None:
                return "no such request"
        elif action == "cancel":
            if self.requests.pop((me, other), None) is None:
                return "no such request"
        elif action == "remove":
            if self.pairs.pop(frozenset((me, other)), None) is None:
                return "not friends"
        else:
            return "unknown action"
        self.save()
        return None


def friends_reply(p, key=None, times=None, friends=None):
    """10419 reply (callback 0x1352f3c, reader 0x1353138; analysis/friends.md
    section 3): u32 count, then per event u32 event id and u32 rows, each
    row in the mail row layout (str name, u32 member id, str, str, u32 0
    (skipped block), str, 7 u32, 4 f32, u32 bool). Since v5.16 the rows are
    the asking player's friends (issue #218) with a stored time on the
    event: rank (from 0) in the 6th u32 (+0x84) and lap ms in the 7th
    (+0x88), as in the 10516 rows (inferred from the field offsets; not
    tested in game); the rest 0. An event with 0 rows still gets its friends
    entry and res_<event>.pld. Request (writer 0x1356af4): u32 n, n x (u32
    event, u32 0), then four id lists (ignored: the server's friends list
    counts), u32 1. An empty reply counts as failed, so a request too
    short to read gets a count of 0 (the phone stores nothing)."""
    try:
        n = struct.unpack_from("<I", p)[0]
        events = [struct.unpack_from("<I", p, 4 + 8 * i)[0] for i in range(min(n, FRIENDS_EVENTS_MAX))]
    except struct.error:
        return blob.u32(0), f"friends: request of {len(p)} bytes not read"
    mine = set(friends.friends_of(key)) if friends and times and key else set()
    body, sent = b"", 0
    for e in events:
        rows = [r for r in times.rows(e, key, friends_ok=True)[0] if r.get("key") in mine] if mine else []
        body += blob.u32(e, len(rows))
        for i, r in enumerate(rows):
            body += (blob.string(r["s1"]) + blob.u32(r["i18"]) + blob.string("") + blob.string("")
                     + blob.u32(0) + blob.string("") + blob.u32(0, 0, 0, 0, 0, i, r["i88"])
                     + struct.pack("<4f", 0, 0, 0, 0) + blob.u32(0))
        sent += len(rows)
    return blob.u32(len(events)) + body, f"friends results for event(s) {events}: {sent} row(s)"


def social_friends_reply(key, times, friends):
    """10556 reply (handler 0x1d07114, analysis/social-login.md section 5):
    u32 1, then per friend u32 member id, u32 n, n x (u32 network type, u32
    length + social id). Field meanings inferred from the request (the
    friends' social ids, sent by SocialMedia::OnFriends); not tested in
    game. Sent: the asking player's friends (issue #218), each with one
    id, type 0 (Facebook, the slot our account uses) "prr:<member>". The
    social ids the phone sends are ignored."""
    out, n = blob.u32(1), 0
    for k in friends.friends_of(key) if friends else []:
        m = times.members.get(k)
        if m:
            out += blob.u32(m, 1, 0) + blob.string(f"prr:{m}")
            n += 1
    return out, f"social friends: sent {n}"


def details_problem(d):
    """Why a stored 10472 entry can't be used, or None (v5.53)."""
    if not isinstance(d, dict):
        return "not an entry"
    def ids(v, most):
        return (isinstance(v, list) and len(v) <= most
                and all(isinstance(i, int) and 0 <= i <= 0xFFFFFFFF for i in v))
    if not (isinstance(d.get("t"), int) and ids(d.get("stats"), DETAILS_STATS)
            and len(d["stats"]) == DETAILS_STATS and ids(d.get("cars"), DETAILS_CARS_MAX)
            and ids(d.get("list2"), DETAILS_LIST2_MAX) and ids([d.get("cars0"), d.get("list2_0")], 2)):
        return "bad fields"
    return None


def details_request(p, cars=None):
    """Read a 10472 request (writer 0x1350ca4 -> 0x13543ac;
    analysis/social-login.md 9.2): u32 page, u32 n + n bytes inner. Inner:
    u32 k + k x (u32 len + id) twice (Game Center, Facebook ids), u32 0,
    the same for Google Play ids, 26 u32 (the player's stats; 27 before
    v5.54, which was wrong: analysis/social-login.md 9.9), u32 len +
    cars blob (u32 head, u32 k, k x u32 car id), u32 len + a second blob of
    the same shape. Returns (values for Friends.set_details, None) or
    (None, why). The inner part must be read to its exact end. Car ids not
    in cars (the game's list, --cars) are dropped (#143 item 5), as the
    phone itself drops unknown ones."""
    try:
        _page, n = struct.unpack_from("<II", p)
        if 8 + n != len(p):
            return None, f"{len(p)} bytes, inner {n}"
        q, i = p[8:], 0

        def u32():
            nonlocal i
            v = struct.unpack_from("<I", q, i)[0]
            i += 4
            return v

        def id_list():
            nonlocal i
            k = u32()
            if k > DETAILS_IDS_MAX:
                raise ValueError(f"{k} social ids")
            for _ in range(k):
                m = u32()
                if m > DETAILS_ID_LEN_MAX or i + m > len(q):
                    raise ValueError(f"social id of {m} bytes")
                i += m

        def ids_blob(most):
            nonlocal i
            m = u32()
            if m < 8 or m % 4 or i + m > len(q):
                raise ValueError(f"list of {m} bytes")
            head, k = struct.unpack_from("<II", q, i)
            if m != 8 + 4 * k or k > most:
                raise ValueError(f"list of {k} ids in {m} bytes")
            v = list(struct.unpack_from(f"<{k}I", q, i + 8))
            i += m
            return head, v

        id_list()
        id_list()
        u32()
        id_list()
        stats = [u32() for _ in range(DETAILS_STATS)]
        cars0, car_ids = ids_blob(DETAILS_CARS_MAX)
        list2_0, list2 = ids_blob(DETAILS_LIST2_MAX)
        if i != len(q):
            return None, f"{len(q) - i} bytes left over"
    except (struct.error, ValueError) as e:
        return None, str(e) or "too short"
    if cars is not None:
        car_ids = [c for c in car_ids if c in cars]
    return dict(stats=stats, cars=list(dict.fromkeys(car_ids)), cars0=cars0,
                list2=list2, list2_0=list2_0), None


def details_ids_blob(head, ids):
    """u32 len + (u32 head, u32 k, k x u32), as the 10472 lists."""
    b = blob.u32(head, len(ids), *ids)
    return blob.u32(len(b)) + b


def friend_details_reply(p, key, times, friends, now=None):
    """10472 reply (callback 0x1354694, analysis/social-login.md 9.2; v5.53,
    issue #278): u32 first 0 (the list is replaced), u32 more 0 (no next
    page), u32 N, then per PRR friend of the asking player: str name, u32
    member id (+0x18), str "" (Game Center), str "prr:<member>" (Facebook
    id, as 10556), u32 0 (skipped block), str "" (Google Play), u32 0 (team:
    no "[tag]" in the name), str "", str "", str "", u32 0, u32 bool; with
    bool 1: u32 seconds since the friend's last 10472, 27 stats (v5.54: the
    friend's request words 1-24, their number of friends, words 25-26;
    analysis/social-login.md 9.9), their
    cars blob and their second blob, as their own phone sent them. A friend
    whose phone never sent 10472 (or who is shadowed) gets bool 0: the game
    shows the name with no stats or cars. The asking player's own request
    is stored first (Friends.set_details), so a player's values are there
    for their friends from their first 10472. Not tested in game."""
    now = int(time.time() if now is None else now)
    stored = ""
    if key != "unknown" and key in times.members:
        d, why = details_request(p, times.cars)
        if d is None:
            stored = f"; request not read ({why})"
        else:
            friends.set_details(key, d, now)
    out, n, full = b"", 0, 0
    for k in sorted(friends.friends_of(key), key=lambda k: times.members.get(k, 0)):
        m = times.members.get(k)
        if not m:
            continue
        d = None if times.hidden(k, key, friends_ok=True) else friends.details.get(k)
        out += (blob.string(times.display_name(k)) + blob.u32(m) + blob.string("")
                + blob.string(f"prr:{m}") + blob.u32(0) + blob.string("") + blob.u32(0)
                + blob.string("") * 3 + blob.u32(0, 1 if d else 0))
        if d:
            st = d["stats"]
            nf = min(len(friends.friends_of(k)), FRIENDS_MAX)
            out += (blob.u32(max(0, now - d["t"]), *st[:DETAILS_FRIENDS_AT], nf, *st[DETAILS_FRIENDS_AT:])
                    + details_ids_blob(d["cars0"], d["cars"])
                    + details_ids_blob(d["list2_0"], d["list2"]))
            full += 1
        n += 1
    return blob.u32(0, 0, n) + out, f"friend details: sent {n} ({full} with stats){stored}"


def friends_board_reply(p, key, times, friends):
    """10486 reply, the friends leaderboard tab (LeaderBoardFriendsSync,
    reader 0xce2510; analysis/social-login.md section 5.2): u32 count, then
    per row str name (+0x00), u32 member id (+0x18), str s2, str s3, u32 0
    (skipped block), str s4, u32 rank from 0 (+0x84), u32 lap ms (+0x88),
    u32 car (+0x8c), f32 PR (+0x90), str s6 (+0x98), u32 i80 (+0x80), str
    tag (+0x68). No header (unlike 10477). Request (writer 0xce2224): u32 a,
    u32 n + n u32 (the event id first, as 10477's), the friend-id block
    (0x1352868, ignored) and more. Rows: the asking player's PRR friends
    with a time on the event, fastest first. Not the player: the game adds
    its own row and numbers the rows by position (v5.27; b48 showed the
    player twice with v5.26)."""
    try:
        n = struct.unpack_from("<I", p, 4)[0]
        event = struct.unpack_from("<I", p, 8)[0] if n else None
    except struct.error:
        return blob.u32(0), f"friends board: request of {len(p)} bytes not read"
    mine = set(friends.friends_of(key)) if friends else set()
    rows = times.rows(event, key, friends_ok=True)[0] if event is not None else []
    rows = [r for r in rows if r.get("key") in mine]
    body = b""
    for i, r in enumerate(rows):
        body += (blob.string(r["s1"]) + blob.u32(r["i18"]) + blob.string(r["s2"]) + blob.string(r["s3"])
                 + blob.u32(0) + blob.string(r["s4"]) + blob.u32(i, r["i88"], r["i8c"])
                 + struct.pack("<f", r["time"]) + blob.string(r["s6"]) + blob.u32(r["i80"])
                 + blob.string(r["s5"]))
    return blob.u32(len(rows)) + body, f"friends board on event {event}: sent {len(rows)}"


def member_rows_request(p):
    """10516 request (writer 0xce45f4): u32 a, u32 n + n u32, u32 m + m
    member ids, then more (0xcf1018, not read). Returns (event candidates,
    member ids); which field holds the event is not confirmed, so the
    first list and a are both tried. None for a request too short."""
    try:
        a, n = struct.unpack_from("<II", p)
        n = min(n, 64)
        first = list(struct.unpack_from(f"<{n}I", p, 8))
        m = min(struct.unpack_from("<I", p, 8 + 4 * n)[0], 64)
        ids = list(struct.unpack_from(f"<{m}I", p, 12 + 4 * n))
    except struct.error:
        return None
    return first + [a], ids


def member_rows_reply(p, key, times):
    """10516 reply (read by 0xce4808): u32 count, then per row str name,
    u32 member id, str s2, str s3, u32 0 (skipped block), str s4, u32 rank
    (from 0), u32 lap ms, u32 car. One row per asked member id with a
    stored time, in the order asked (the callback 0xde13cc wants you
    first, then the rival)."""
    req = member_rows_request(p)
    if req is None:
        return blob.u32(0), f"member rows: request of {len(p)} bytes not read"
    events, ids = req
    event = next((e for e in events if str(e) in times.data and e not in IGNORED_EVENTS), None)
    rows = times.rows(event, key, friends_ok=True)[0] if event is not None else []
    by_member = {r["i18"]: r for r in rows if r.get("key")}    # real rows only
    out = [by_member[i] for i in ids if i in by_member]
    body = b"".join(blob.string(r["s1"]) + blob.u32(r["i18"]) + blob.string("") + blob.string("")
                    + blob.u32(0) + blob.string("") + blob.u32(r["i84"], r["i88"], r["i8c"])
                    for r in out)
    return blob.u32(len(out)) + body, f"member rows {ids} on event {event}: sent {len(out)}"


# Track ids in the phone's Tracks/ttk.dat.nct (analysis/online-multiplayer.md
# Q7); the schedule's track lookup 0x1422da4 only finds these.
TRACK_IDS = frozenset([21, 22, 24, 26, *range(29, 33), *range(38, 48), *range(49, 58), 59, 60,
                       62, *range(64, 105), *range(111, 117), 122, *range(126, 129), 130,
                       *range(133, 137), *range(139, 170), *range(171, 217)])
SCHEDULE_VERSION = 4            # 10536 reply field 1; anything else is read as a status


def omp_groups(path):
    """Car groups of a decrypted data/onlinemp.dat (RRCE v5): {key: [car ids]}."""
    d = open(path, "rb").read()
    if d[:4] != b"RRCE":
        raise ValueError(f"{path}: not a decrypted onlinemp.dat (decrypt it with rr3_nct.py)")
    n = struct.unpack_from("<I", d, 8)[0]
    i, out = 12, {}
    for _ in range(n):
        key, i = read_string(d, i)
        k = struct.unpack_from("<I", d, i)[0]
        out[key] = list(struct.unpack_from(f"<{k}I", d, i + 4))
        i += 4 + 4 * k
    return out


# What an entry of `events` may set (v5.18); the rest of the file's keys
# are defaults for every event, except `week` (each event's own, else the
# window number) and `seconds` (one length for all, so windows stay aligned).
OMP_EVENT_KEYS = ("name", "week", "cars", "races", "reward", "place_rewards", "period",
                  "leagues", "league_rewards",      # v5.48 (#264): one car group / reward per league
                  "ios_cars", "ios_leagues")        # v5.66: iPhones' groups (they lack our PRR_ groups)
PRR_GROUP = "PRR_"              # our own car groups (#383), only in the asset update's onlinemp.dat


def check_event(ev, what, groups):
    """Check one OMP event (the whole file, or one entry of `events`
    merged with the file's defaults); fills in `cars` for a v5.14 file."""
    races = ev.get("races", [])
    if len(races) != 3:
        raise ValueError(f"{what}: needs exactly 3 races, has {len(races)}")
    for n, r in enumerate(races, 1):
        race = f"{what}: race {n} ({r.get('name', '?')})"
        if r.get("track") not in TRACK_IDS:
            raise ValueError(f"{race}: track {r.get('track')} is not a track id in ttk.dat")
        if "cars" in r and "cars" in ev:
            raise ValueError(f"{race}: cars belongs to the event since v5.15 (the game uses one car "
                             "group for all three races); remove it from the race")
    if "leagues" in ev:                 # v5.48 (#264)
        lg = ev["leagues"]
        if not isinstance(lg, list) or len(lg) != OMP_LEAGUES_N or not all(isinstance(g, str) and g for g in lg):
            raise ValueError(f"{what}: leagues must be a list of {OMP_LEAGUES_N} car-group keys (league 1, 2, 3)")
        for n, g in enumerate(lg, 1):
            if groups is not None and g not in groups:
                raise ValueError(f"{what}: league {n} car group {g} is not in onlinemp.dat")
        if "cars" not in ev and not races[0].get("cars"):
            ev["cars"] = lg[0]
    if "league_rewards" in ev:
        lr = ev["league_rewards"]
        if (not isinstance(lr, list) or len(lr) != OMP_LEAGUES_N
                or not all(isinstance(r, int) and not isinstance(r, bool) and r >= 0 for r in lr)):
            raise ValueError(f"{what}: league_rewards must be {OMP_LEAGUES_N} whole numbers, 0 or more")
    if "cars" not in ev:
        ev["cars"] = races[0].get("cars")
    if not isinstance(ev["cars"], str) or not ev["cars"]:
        raise ValueError(f"{what}: cars must be a car-group key from onlinemp.dat")
    if groups is not None and ev["cars"] not in groups:
        raise ValueError(f"{what}: car group {ev['cars']} is not in onlinemp.dat")
    ios = []                            # v5.66: iPhones' groups
    if "ios_leagues" in ev:
        lg = ev["ios_leagues"]
        if not isinstance(lg, list) or len(lg) != OMP_LEAGUES_N or not all(isinstance(g, str) and g for g in lg):
            raise ValueError(f"{what}: ios_leagues must be a list of {OMP_LEAGUES_N} car-group keys (league 1, 2, 3)")
        ios += [(f"ios_leagues league {n}", g) for n, g in enumerate(lg, 1)]
    if "ios_cars" in ev:
        if not isinstance(ev["ios_cars"], str) or not ev["ios_cars"]:
            raise ValueError(f"{what}: ios_cars must be a car-group key from onlinemp.dat")
        ios.append(("ios_cars", ev["ios_cars"]))
    for name, g in ios:
        if g.startswith(PRR_GROUP):
            raise ValueError(f"{what}: {name} {g} is one of our {PRR_GROUP} groups, which iPhones don't have")
        if groups is not None and g not in groups:
            raise ValueError(f"{what}: {name} car group {g} is not in onlinemp.dat")
    used = [ev["cars"]] + list(ev.get("leagues") or [])
    prr = sorted({g for g in used if g.startswith(PRR_GROUP)})
    if prr and not ios:
        raise ValueError(f"{what}: {', '.join(prr)} needs ios_cars or ios_leagues (a group iPhones have): "
                         "iPhones don't get our groups file and crash without the group (#383)")
    if "period" in ev and (not isinstance(ev["period"], int) or ev["period"] < 1):
        raise ValueError(f"{what}: period must be a whole number of seconds, at least 1")
    if ev.get("week", 1) == -1:
        raise ValueError(f"{what}: week must not be -1")


def load_schedule(path, groups=None):
    """Read and check an OMP schedule file (rr3-omp-schedule.example.json).
    `cars` is one car group for the whole event (v5.15). A file made for
    v5.14 or older (a `cars` per race, none for the event) still loads:
    race 1's group is used, the one the game showed. With `events` (v5.18)
    each entry is one event, answered in turn, one per window of `seconds`
    (window n gets entry n % count); `_events` keeps them merged."""
    cfg = json.load(open(path))
    if not isinstance(cfg.get("seconds", 604800), int) or cfg.get("seconds", 604800) < 900:
        raise ValueError(f"{path}: seconds must be a whole number of at least 900")
    off = cfg.get("offset", 0)              # v5.75 (#574)
    if not isinstance(off, int) or isinstance(off, bool) or not 0 <= off < cfg.get("seconds", 604800):
        raise ValueError(f"{path}: offset must be a whole number of seconds from 0 to seconds - 1")
    if "events" not in cfg:
        check_event(cfg, path, groups)
        return cfg
    events = cfg["events"]
    if not isinstance(events, list) or not events:
        raise ValueError(f"{path}: events must be a list of at least one event")
    defaults = {k: v for k, v in cfg.items() if k in OMP_EVENT_KEYS and k not in ("week", "name")}
    cfg["_events"] = []
    for n, e in enumerate(events, 1):
        what = f"{path}: event {n} ({e.get('name', '?')})" if isinstance(e, dict) else f"{path}: event {n}"
        if not isinstance(e, dict):
            raise ValueError(f"{what}: must be an object")
        extra = sorted(set(e) - set(OMP_EVENT_KEYS))
        if extra:
            raise ValueError(f"{what}: {', '.join(extra)} can't be set per event (only {', '.join(OMP_EVENT_KEYS)})")
        ev = dict(defaults, **e)
        if "cars" not in e and any("cars" in r for r in e.get("races", []) if isinstance(r, dict)):
            ev.pop("cars", None)            # a v5.14-style event: its races' cars, not the default
        check_event(ev, what, groups)
        cfg["_events"].append(ev)
    return cfg


def omp_event_start(cfg, now):
    """Start of the current event window: a multiple of the event length
    (`seconds`, default 7 days) after `offset` (v5.75) in Unix time, the
    same for every phone."""
    length = cfg.get("seconds", 7 * 24 * 3600)
    return now - (now - cfg.get("offset", 0)) % length


def omp_event(cfg, now):
    """The event answered at server time now: the schedule itself, or
    (v5.18, `events`) entry n % count for window n = (now - offset) // seconds, with
    the window number as its week id unless the entry sets one. Keys:
    those of the schedule (seconds, cars, races, ...), plus `_index`."""
    if "_events" not in cfg:
        return cfg
    n = (now - cfg.get("offset", 0)) // cfg.get("seconds", 7 * 24 * 3600)
    i = n % len(cfg["_events"])
    ev = cfg["_events"][i]
    return dict(ev, seconds=cfg.get("seconds", 7 * 24 * 3600), offset=cfg.get("offset", 0),
                week=ev.get("week", n), _index=i)


def omp_event_label(cfg, now):
    """Log text: the week, and with `events` which one (v5.18)."""
    ev = omp_event(cfg, now)
    if "_index" not in ev:
        return f"OMP schedule week {ev.get('week', 1)}"
    return (f"OMP schedule week {ev['week']}, event {ev['_index'] + 1} of {len(cfg['_events'])} "
            f"({ev.get('name', ev['cars'])})")


def schedule_reply(cfg, now=None, league=1, ios=False):
    """10536 reply, read by 0xf711fc (44 fields, analysis/online-multiplayer.md
    "10536 schedule"). The three car lists are one per league (0xf746ec);
    the game only asks for league 1, so the event's group goes in all
    three (v5.15). Field 19 is the race rotation period. Fields marked
    unknown in the note are sent as 0. Fields 3 and 44 (seconds the event
    lasts after this reply) count to the end of the shared window (v5.4;
    v5.3 sent the full length from each reply, so each phone's race
    rotation ran from its own sync, inferred from the 2026-10-21 test).
    With `events`, the current window's event is answered (v5.18).
    v5.48 (#264): league (1-3) picks the event's `leagues` group for fields
    4-6 and its `league_rewards` entry for field 7 (else `cars` / `reward`).
    v5.66: ios = an iPhone asks; its group is `ios_leagues` (that league's),
    else `ios_cars`, else the same as everyone's."""
    now = int(time.time()) if now is None else now
    cfg = omp_event(cfg, now)
    i = min(max(int(league), 1), OMP_LEAGUES_N) - 1
    cars = cfg["leagues"][i] if cfg.get("leagues") else cfg["cars"]
    if ios and cfg.get("ios_leagues"):
        cars = cfg["ios_leagues"][i]
    elif ios and cfg.get("ios_cars"):
        cars = cfg["ios_cars"]
    reward = cfg["league_rewards"][i] if cfg.get("league_rewards") else cfg.get("reward", 2000)
    races = cfg["races"]
    secs = omp_event_start(cfg, now) + cfg.get("seconds", 7 * 24 * 3600) - now
    places = (list(cfg.get("place_rewards", [])) + [0] * 10)[:10]
    out = blob.u32(SCHEDULE_VERSION, cfg.get("week", 1), secs)               # 1-3
    out += blob.string(cars) * 3                                            # 4-6
    out += blob.u32(*places, reward)                                        # 7-17
    out += blob.string("") + blob.u32(cfg.get("period", 0))                 # 18, 19
    for r in races:                                                         # 20-31
        out += blob.u32(r["track"], r.get("laps", 3), *(list(r.get("settings", [])) + [0, 0])[:2])
    out += blob.u32(*[0] * 5)                                               # 32-36
    out += blob.u32(0, 0 if reward else 1, 0, 0)                            # 37-40
    out += blob.u32(0, 0, 0, secs)                                          # 41-44
    return out


# The game's current OMP race (0xf74168, called with league 1 by the
# matchmaking screen 0xf36d14): (league + (server time + OMP_ScheduleOffset)
# / period) % 3; period = 10536 field 19 (schedule `period`, else 0) or
# 300 s below 1. OMP_ScheduleOffset is a server variable we don't send (0
# assumed).
OMP_PERIOD = 300
OMP_LEAGUE = 1


def omp_period(cfg):
    """Seconds per race, as the game reads 10536 field 19."""
    return cfg.get("period", 0) if cfg.get("period", 0) >= 1 else OMP_PERIOD


def omp_current_race(cfg, now):
    """Index of the schedule race the game shows at server time now: the
    game's own rule, counted from 1970 (v5.15; v5.4 to v5.14 counted from
    the event start, the same for 300 s and a length that is a multiple of
    900 s, but not for every `period`)."""
    return (OMP_LEAGUE + now // omp_period(omp_event(cfg, now))) % 3


def omp_rotation(cfg, now):
    """Log text: server time, second of the slot, the race we pick (for
    comparing with the race the phone's pop-up shows, issue #86)."""
    cfg = omp_event(cfg, now)
    i, period = omp_current_race(cfg, now), omp_period(cfg)
    return f"time {now}, second {now % period} of {period}, race {i} track {cfg['races'][i]['track']}"


def start_match_reply(cfg, p, now, store=None, member=None):
    """10626 (StartMatch) reply, read by 0xce76a8; the game's checks
    (0xf7acd4): match id, track and laps not 0, field 5 = the week id the
    request sent (its field 4), at least one other player in the room.
    Request (writer 0xce70f8): u32 7469, 2 u32, week, u32, flag, local
    slot, n players, n x (u32 player value, u32 car), ... The match goes
    into store (v5.47, #360; default OMP_STORE) as an open match; member =
    the asking phone's member id (None = not checked). Returns (reply, log
    text); (None, text) for a request too short to read."""
    if len(p) < 32:
        return None, f"StartMatch request of {len(p)} bytes not read"
    week, n = struct.unpack_from("<I", p, 12)[0], struct.unpack_from("<I", p, 28)[0]
    slot = struct.unpack_from("<I", p, 24)[0]
    n = min(n, 43, (len(p) - 32) // 8)
    rows = [struct.unpack_from("<2I", p, 32 + 8 * i) for i in range(n)]       # (value, car)
    ids = sorted(v for v, _car in rows)
    cfg = omp_event(cfg, now)
    race = cfg["races"][omp_current_race(cfg, now)]
    sel = OMP_SELECTOR[0].room_for([v for v in ids if 0 < v < GUEST_VALUE], now)     # v5.60 (#469)
    if sel:
        race = dict(race, track=sel[0], laps=sel[1])
    # Same id for every phone of one match: from the week, the rotation slot
    # and the players' values (the same roster on every phone).
    match = zlib.crc32(struct.pack(f"<II{n}I", week, now // omp_period(cfg), *ids)) & 0x7FFFFFFF or 1
    sender = rows[slot][0] if slot < n else None
    note = (store or OMP_STORE[0]).started(week, rows, match, race["track"], race.get("laps", 3), now,
                                           sender, member, selector=bool(sel))
    out = blob.u32(match, race["track"], race.get("laps", 3), 0, week, 0, 0, 0, 0)   # n = 0 players
    return out, (f"OMP StartMatch: match {match}, {n} players {', '.join(map(str, ids))}, "
                 f"track {race['track']}, laps {race.get('laps', 3)}; "
                 + ("Race Selector P2P room (MP), unranked; " if sel else "") + omp_rotation(cfg, now)
                 + (f"; {note}" if note else ""))


OMP_RATING = 1000                       # FinishedMatch row rating before and after (v5.67, #521; v5.20: column 9)
OMP_RATING_TEST = [False]               # --omp-rating-test (v5.43, #262)
OMP_NO_TIME = 0xFFFFFFFF                # a FinishedMatch time not known yet
MATCH_KEEP_S = 2 * 3600                 # a settled match's StartMatch head is kept this long for late reports
MATCH_MAX = 1000                        # open (not yet settled) matches at most; the oldest is settled early
GUEST_VALUE = 0x80000000                # a player value at or above this is a starter without a member

# Settle (v5.47, #360; #359 "No waiting at race end"): a room is settled when
# every starter has reported, or SETTLE_AFTER_S after its first report with
# a finished row (v5.82; v5.47-v5.81: any first report, a quitter's too), at
# the latest settle_cap(laps) after its start (v5.78, #86: laps x
# SETTLE_LAP_S, between SETTLE_CAP_MIN_S and SETTLE_CAP_MAX_S; was a flat 600).
SETTLE_AFTER_S = 300                    # v5.82 (Tom 2026-11-10: 5 min; was 120)
SETTLE_LAP_S = 300                      # Tom 2026-11-09: about 5 min per lap
SETTLE_CAP_MIN_S = 600                  # short races keep the old 10 min
SETTLE_CAP_MAX_S = 3600
SETTLE_TICK_S = 15                      # the timer thread checks this often
LAP_CAP_MS = 10 * 60 * 1000             # a race time above laps x this is no time (DNF, #143)
MIN_LAP_MS = 30 * 1000                  # v5.82 (#360): a race time below laps x this is no time (DNF)


def settle_cap(laps):
    """Seconds after a room's start at which it is settled at the latest
    (v5.78, #86): laps x 5 min, kept between 10 and 60 min. Unknown or
    bad laps give the 10 min floor."""
    try:
        n = max(int(laps or 0), 0)
    except (TypeError, ValueError):
        n = 0
    return min(max(n * SETTLE_LAP_S, SETTLE_CAP_MIN_S), SETTLE_CAP_MAX_S)

OMP_AGREE_MS = 1000                     # v5.84 (#606 O2): own time vs another phone's view of it
OMP_LATE_S = 180                        # v5.84 (#606 O3): finish reported this long after start + time
OMP_EARLY_S = 5                         # v5.84 (#606 O3): or this much before start + time (impossible)
OMP_DNF_TIME = 0xFFFFFFFE               # a reply time the results screen shows as DNF (v5.67, #521)

# Status of a FinishedMatch row by its 2nd u32, the phone's status code
# (v5.67, #521; analysis/online-multiplayer.md "FinishedMatch reply rows":
# map omp+0x5c8, built by 0xf7d894 from the roster flags). 0 = nothing yet.
# A code not listed (4: [slot+0x7f], not traced) reads as "finished" with
# its time, checked at settle by v5.51's time rule (OmpStore.settle).
OMP_ST_NONE, OMP_ST_FINISHED, OMP_ST_LEFT, OMP_ST_DISCONNECTED = 0, 1, 2, 3
OMP_STATUS = {OMP_ST_NONE: "dnf", OMP_ST_FINISHED: "finished", OMP_ST_LEFT: "left",
              OMP_ST_DISCONNECTED: "dnf"}


def omp_time_ok(ms, laps, track=None):
    """A race time the server takes: known, > 0, at least laps x
    MIN_LAP_MS (v5.82, #360) and at most laps x LAP_CAP_MS (#143). v5.86
    (#606 O1): with the track id, at least laps x the track's minimum lap
    (--lb-floors) when that is higher."""
    try:
        n = max(int(laps or 0), 1)
    except (TypeError, ValueError):
        n = 1
    lap_min = MIN_LAP_MS
    if track is not None and FLOORS[0] is not None:
        lap_min = max(lap_min, FLOORS[0].omp_floor(track) or 0)
    return ms is not None and ms != OMP_NO_TIME and 0 < ms and n * lap_min <= ms <= n * LAP_CAP_MS


def omp_row_status(code, ms, flag, laps, track=None):
    """(status, time ms or None) for one FinishedMatch row (v5.47, #360;
    v5.67: by the status code, #521): OMP_STATUS[code], a code not listed
    = "finished"; a finished row with no time, a time below laps x
    MIN_LAP_MS (v5.82) or above laps x LAP_CAP_MS is dnf (#143); a status
    other than finished keeps no time.
    The flag ([slot+0x7e], disconnected) is not used: the phone already
    turns it into code 3."""
    status = OMP_STATUS.get(code, "finished")
    if status == "finished" and not omp_time_ok(ms, laps, track):     # v5.86: track floor (O1)
        return "dnf", None
    return status, ms if status == "finished" else None


def omp_member(value):
    """Member id of a player value; 0 for a starter without one (a guest)."""
    return value if FIRST_MEMBER <= value < GUEST_VALUE else 0


def utc_date(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d")


OMP_LEAGUES_N = 3
OMP_UNLOCK_AT = (0, 10, 20)             # finished races to open league 1, 2, 3 (#264; #258 B1)


class OmpLeagues:
    """OMP leagues (v5.48, issue #264). path (--omp-leagues,
    data/rr3-omp-leagues.json): {"<member>": {"pick": 0-3, "served": 1-3,
    "at": time}}; pick 0 = automatic (the highest unlocked league), served =
    the league of the member's last 10536 (rr3_mp_server.py splits rooms by
    it). A league is unlocked by races_finished (#360): league 2 at 10,
    league 3 at 20, never locked again. None = memory only. The caller
    holds the server lock.

    v5.50 (#383): an admin "force": 1-3 (edited by hand, never by the API)
    puts the member in that league whatever their unlocks. The file is read
    again when it changes on disk (checked at most once a second)."""

    def __init__(self, path=None, log=print):
        self.path, self.log, self.data = path, log, {}
        self.sig, self.checked = None, 0.0
        self.reload(force=True)

    def file_sig(self):
        try:
            st = os.stat(self.path)
            return st.st_mtime_ns, st.st_size
        except OSError:
            return None

    def reload(self, force=False):
        """Read the file again if it changed since we read or wrote it."""
        if not self.path or (not force and time.time() - self.checked < 1):
            return
        self.checked = time.time()
        sig = self.file_sig()
        if sig == self.sig and not force:
            return
        self.sig = sig
        if sig is None:
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("not an object")
            self.data = {k: v for k, v in data.items() if isinstance(v, dict)}
        except (OSError, ValueError) as e:
            self.log(f"omp leagues {self.path}: not read ({e}); "
                     + ("every member starts in league 1" if force else "keeping the last good copy"))

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1, sort_keys=True)
        os.replace(tmp, self.path)
        self.sig = self.file_sig()

    @staticmethod
    def unlocked(races):
        """The highest league open after races finished races."""
        return sum(1 for n in OMP_UNLOCK_AT if races >= n)

    def forced(self, member):
        f = self.data.get(str(member), {}).get("force")
        return f if f in range(1, OMP_LEAGUES_N + 1) else None

    def pick(self, member):
        self.reload()
        p = self.data.get(str(member), {}).get("pick", 0)
        return p if p in range(OMP_LEAGUES_N + 1) else 0

    def served(self, member):
        self.reload()
        v = self.data.get(str(member), {}).get("served")
        return v if v in range(1, OMP_LEAGUES_N + 1) else 1

    def league_for(self, member, races):
        """The league a member races in: their pick if it is unlocked,
        else (automatic, or a pick that isn't) the highest unlocked."""
        top, p = self.unlocked(races), self.pick(member)
        f = self.forced(member)
        if f:
            return f
        return p if 1 <= p <= top else top

    def serve(self, member, races, now):
        """The member's league for a 10536 answer; written to the file as
        `served` only when it changed."""
        league = self.league_for(member, races)
        e = self.data.get(str(member))
        if e is None or e.get("served") != league:
            e = self.data.setdefault(str(member), {"pick": 0})
            e["served"], e["at"] = league, int(now)
            self.save()
        return league

    def set_pick(self, member, league, races, now):
        """Store a pick (0 = automatic). Returns None, or why it was refused."""
        if league not in range(OMP_LEAGUES_N + 1):
            return "league must be 0 (automatic), 1, 2 or 3"
        if league > self.unlocked(races):
            return f"league {league} is locked"
        e = self.data.setdefault(str(member), {})
        e["pick"], e["at"] = league, int(now)
        e.setdefault("served", 1)
        self.save()
        return None

    def info(self, member, races):
        """GET /prr/api/me/league: the member's league and the unlocks."""
        top = self.unlocked(races)
        return {"league": self.league_for(member, races), "pick": self.pick(member), "served": self.served(member),
                "forced": self.forced(member),
                "unlocked": top, "races_finished": races,
                "next_unlock_at": OMP_UNLOCK_AT[top] if top < OMP_LEAGUES_N else None,
                "unlock_at": list(OMP_UNLOCK_AT)}


OMP_LEAGUES = [OmpLeagues()]            # replaced by main() with the file-backed one


# OMP invites (v5.56, issue #427 phase 2; analysis/online-multiplayer.md "OMP invites")
INVITE_TTL_S = 15 * 60                  # Tom, 2026-11-07: 15 min (MP --private-ttl)
INVITE_GROUP_S = 2 * 3600               # a match this soon after an invite can be that group's private race
INVITE_ROOMS_MAX = 2000                 # rooms kept at most (oldest dropped)
INVITE_LINK_RE = re.compile(r"MultiplayerInvite/(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5}):(-?\d{1,10}):(-?\d{1,10}):"
                            r"(-?\d{1,10}):(-?\d{1,10})", re.I)
INVITE_NEWS_BASE = 0x40000000           # news item id = base + room id % 2^30 (never one of EA's small ids)
APP_PACKAGE = "com.ea.games.r3_row"


def parse_invite_request(p):
    """10455 request (SyncUserPNE, serializer 0xcf1a28): u32 invitee member
    id, u32 notice template (91184), u32 len + link, then the text
    replacements (u32 n, n x (str, str); u32 n, n x (str, u32)). Returns
    (invitee, link fields dict) or (None, why). Only the first three are
    used; the link must match INVITE_LINK_RE (numeric IP, six fields)."""
    try:
        invitee, template, n = struct.unpack_from("<III", p)
        if n > 512 or 12 + n > len(p):
            return None, f"link of {n} bytes"
        link = p[12:12 + n].decode("ascii", "replace")
    except struct.error:
        return None, f"request of {len(p)} bytes"
    m = INVITE_LINK_RE.search(link)
    if not m:
        return None, f"link not understood: {link[:80]!r}"
    host, port, room, key, event, n6 = m.groups()
    if any(int(x) > 255 for x in host.split(".")):
        return None, "bad IP in the link"
    return invitee, dict(host=host, port=int(port), room=int(room), key=int(key) & 0xFFFFFFFF,
                         event=int(event), n=int(n6), template=template)


def invite_link(r):
    """The rr3:// link the game's invite popup reads (0xf790ac):
    MultiplayerInvite/<IP>:<port>:<room>:<pass key>:<event>:<n>."""
    return f"rr3://MultiplayerInvite/{r['host']}:{r['port']}:{r['room']}:{r['key']}:{r['event']}:{r['n']}"


def invite_intent(link, text):
    """An Android intent:// link for a web page: opens the game's launch
    screen with the extras MainActivity.HandleLaunchURL reads (deepLinkUrl,
    alert); Chrome needs it to set extras (not tested in game)."""
    q = lambda v: urllib.parse.quote(v, safe="")
    return (f"intent://MultiplayerInvite#Intent;scheme=rr3;package={APP_PACKAGE};"
            f"S.deepLinkUrl={q(link)};S.alert={q(text)};end")


class OmpInvites:
    """OMP invites (v5.56, issue #427 phase 2). path (--omp-invites, private,
    mode 0600): {"<room id>": {"owner", "members": [invitees], "host",
    "port", "room", "key", "event", "n", "created", "expires"}};
    rr3_mp_server.py (--invites) reads "members" to admit only invitees.
    rooms_path (--omp-private-rooms): the open private rooms MP v0.24
    writes; a 10455 for a room not there with this host is refused (no
    file = refused). The caller holds the server lock."""

    def __init__(self, path=None, rooms_path=None):
        self.path, self.rooms_path = path, rooms_path
        try:
            d = json.load(open(path)) if path else {}
        except (OSError, ValueError):
            d = {}
        self.rooms = {k: v for k, v in d.items() if isinstance(v, dict) and k.isdigit()}

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(self.rooms, f, indent=1, sort_keys=True)
        os.replace(tmp, self.path)

    def mp_room(self, room_id):
        """MP's entry for an open private room, or None."""
        try:
            d = json.load(open(self.rooms_path)) if self.rooms_path else {}
        except (OSError, ValueError):
            return None
        r = d.get(str(room_id)) if isinstance(d, dict) else None
        return r if isinstance(r, dict) else None

    def prune(self, now):
        """Drop invites past INVITE_GROUP_S (kept that long for the private
        match check, though they can't be joined after `expires`)."""
        old = [k for k, r in self.rooms.items() if now - r.get("created", 0) > INVITE_GROUP_S]
        for k in old:
            del self.rooms[k]
        if len(self.rooms) > INVITE_ROOMS_MAX:
            for k in sorted(self.rooms, key=lambda k: self.rooms[k].get("created", 0))[:len(self.rooms) - INVITE_ROOMS_MAX]:
                del self.rooms[k]
        return bool(old)

    def add(self, owner, invitee, f, now, friends_ok=True):
        """A host's invite (one 10455). Returns a note for the log."""
        if not owner:
            return "invite not kept: sender has no member id"
        if not friends_ok:
            return f"invite not kept: member {invitee} is not a PRR friend of {owner}"
        mp = self.mp_room(f["room"])
        if mp is None:
            return f"invite not kept: room {f['room']} is not an open MP private room"
        if mp.get("owner") != owner:
            return f"invite not kept: room {f['room']} belongs to member {mp.get('owner')}, not {owner}"
        self.prune(now)
        k = str(f["room"])
        r = self.rooms.get(k)
        if r is None or r.get("key") != f["key"]:
            r = self.rooms[k] = dict(owner=owner, members=[], host=f["host"], port=f["port"], room=f["room"],
                                     key=f["key"], event=f["event"], n=f["n"], created=int(now),
                                     expires=int(now) + INVITE_TTL_S, league=mp.get("league"))
        if invitee not in r["members"]:
            if len(r["members"]) >= ROOM_INVITES_MAX:
                return f"invite not kept: room {k} already has {ROOM_INVITES_MAX} invitees"
            r["members"].append(invitee)
        self.save()
        return f"invite: room {k}, member {owner} invited {invitee}"

    def pending(self, member, now):
        """Invites member can still join, oldest first."""
        return sorted((r for r in self.rooms.values() if member in r.get("members", ()) and now < r.get("expires", 0)),
                      key=lambda r: r["created"])

    def is_private(self, members, now):
        """True when members (the match's member ids) are one invite group:
        the host plus some of their invitees, the invite made at most
        INVITE_GROUP_S ago."""
        ms = {m for m in members if m}
        if len(ms) < 2:
            return False
        for r in self.rooms.values():
            group = {r.get("owner")} | set(r.get("members", ()))
            if r.get("owner") in ms and ms <= group and now - r.get("created", 0) <= INVITE_GROUP_S:
                return True
        return False


ROOM_INVITES_MAX = 42                   # the game's lobby has 43 slots, host included
OMP_INVITES = [OmpInvites()]            # replaced by main() with the file-backed one

SELECTOR_ROOM_S = 30 * 60               # a selector room's StartMatch comes within this of its lock (MP keeps 30 min)


class OmpSelectorRooms:
    """Race Selector P2P rooms (v5.60, issue #469), read from
    rr3_mp_server.py v0.26's --selector-rooms file (never written here):
    {"<created>-<n>": {"members", "track", "laps", "event", "created"}}.
    Read again when it changes; no file = no selector rooms."""

    def __init__(self, path=None):
        self.path, self.mtime, self.rooms = path, None, {}

    def load(self):
        if not self.path:
            return {}
        try:
            mtime = os.path.getmtime(self.path)
            if mtime != self.mtime:
                data = json.load(open(self.path))
                self.mtime, self.rooms = mtime, data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            self.mtime, self.rooms = None, {}
        return self.rooms

    def room_for(self, members, now):
        """(track, laps) of the selector room these member ids raced in, or
        None: a room locked at most SELECTOR_ROOM_S ago with exactly these
        members, else the newest one holding them all (a phone without a
        member id isn't in MP's list)."""
        ms = {m for m in members if 0 < m < GUEST_VALUE}           # guests aren't in MP's list
        if not ms:
            return None
        exact, holding = [], []
        for r in self.load().values():
            if not isinstance(r, dict) or not 0 <= now - r.get("created", -SELECTOR_ROOM_S - 1) <= SELECTOR_ROOM_S:
                continue
            track, laps, rm = r.get("track"), r.get("laps"), r.get("members")
            if not (isinstance(track, int) and isinstance(laps, int) and 1 <= laps <= 99 and isinstance(rm, list)):
                continue
            if set(rm) == ms:
                exact.append((r["created"], track, laps))
            elif ms <= set(rm):
                holding.append((r["created"], track, laps))
        pick = max(exact or holding, default=None)
        return pick[1:] if pick else None


OMP_SELECTOR = [OmpSelectorRooms()]     # replaced by main() with the file-backed one


# --- OMP ratings (v5.79, issue #263; #258 A2-A8, #359 d12) -------------------
RATING_START = 1000                     # everyone starts here (A4)
RATING_K = 32                           # A2: change_i = round(K / (n - 1) x sum_j (S_ij - E_ij))
RATING_FLOOR = 100
RATINGS_VERSION = 1                     # the ratings files' "version"
RATINGS_MODES = ("off", "shadow", "on")


def rating_round(x):
    """Half away from zero (Python's round() would send +0.5 to 0)."""
    return int(math.copysign(math.floor(abs(x) + 0.5), x))


def rating_expect(r_i, r_j):
    """E_ij: i's expected score against j (Elo, 400 points)."""
    return 1.0 / (1.0 + 10.0 ** ((r_j - r_i) / 400.0))


def rating_changes(players, snap):
    """Rating changes of one settled room (#263 items 6-7; Tom 2026-11-09
    decisions 2-3). players = the record's rows (member, status, position),
    snap = {member: rating at the room's start}; a guest or a member not in
    snap counts as RATING_START. Returns (quorum, {index in players:
    change}): only the rows that are rated.
    - Quorum (A3): finishers > starters / 2. Then every starter is rated
      against every other: finishers by position, everyone else (dnf =
      a dropped phone, left) tied last; n = all starters.
    - No quorum: only a player who left (status "left") is rated, losing to
      every finisher (n = the finishers + them); the finishers and dnf
      players don't change (decision 3: a dropped phone, no penalty)."""
    def r(p):
        m = p.get("member") or 0
        return snap.get(m, RATING_START) if m else RATING_START

    def rank(p):
        return p["position"] if p["status"] == "finished" else 1 << 30
    fin = [i for i, p in enumerate(players) if p["status"] == "finished"]
    n = len(players)
    quorum = n >= 2 and 2 * len(fin) > n
    out = {}
    if quorum:
        for i, p in enumerate(players):
            s = 0.0
            for j, q in enumerate(players):
                if i != j:
                    sij = 1.0 if rank(p) < rank(q) else 0.5 if rank(p) == rank(q) else 0.0
                    s += sij - rating_expect(r(p), r(q))
            out[i] = rating_round(RATING_K / (n - 1) * s)
        return True, out
    for i, p in enumerate(players):
        if p["status"] == "left" and fin:
            s = sum(0.0 - rating_expect(r(p), r(players[j])) for j in fin)
            out[i] = rating_round(RATING_K / len(fin) * s)       # n - 1 = the finishers
    return False, out


class OmpRatings:
    """OMP ratings (v5.79, issue #263): the switch, the files and the maths.

    mode (--ratings): "off" = nothing rated, nothing written; "shadow" =
    rooms are rated into shadow_path / shadow_log only (never sent or
    served); "on" = rated into path, sent in FinishedMatch, served by
    /prr/api/ratings. start (--ratings-start, "YYYY-MM-DD"): the date shown
    on the site; with "shadow" it is also the switch: from 00:00 UTC that
    day the mode is "on" with no restart (Tom 2026-11-09, decision 5). A
    room is rated in the mode it started in (its snapshot), so a room that
    started in shadow stays unranked.

    Files (one JSON object, written to .tmp then renamed, so a copy taken
    at any time is whole): {"version": 1, "mode", "updated",
    "players": {"<member>": {"rating", "races", "finished", "updated"}}}.
    The real file is never reset once on; it starts empty, so everyone is
    at 1000 when ratings go on (the shadow file is never read in on).
    shadow_log: one line per rated room in shadow. None = memory only.
    The caller holds the server lock."""

    def __init__(self, path=None, shadow_path=None, shadow_log=None, mode="off", start=None, log=print):
        if mode not in RATINGS_MODES:
            raise ValueError(f"ratings mode {mode!r}: not off, shadow or on")
        self.start_ts = None
        if start:
            d = datetime.datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
            self.start_ts = int(d.timestamp())
        self.path, self.shadow_path, self.shadow_log = path, shadow_path, shadow_log
        self.mode, self.start, self.log = mode, start, log
        self.tables = {"on": self.read(path), "shadow": self.read(shadow_path)}
        self.board = None               # the "on" table sorted, rebuilt after a change

    def read(self, path):
        if not path:
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return {}
        players = data.get("players") if isinstance(data, dict) else None
        if not isinstance(players, dict):
            raise ValueError(f"{path}: not a ratings file (no \"players\")")
        return {int(m): dict(v) for m, v in players.items()}

    def write(self, which, now):
        path = self.path if which == "on" else self.shadow_path
        if not path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        data = {"version": RATINGS_VERSION, "mode": which, "updated": int(now),
                "players": {str(m): v for m, v in sorted(self.tables[which].items())}}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        os.replace(tmp, path)

    def mode_at(self, now):
        """The mode in force at now: shadow turns on at --ratings-start."""
        if self.mode == "shadow" and self.start_ts is not None and now >= self.start_ts:
            return "on"
        return self.mode

    def rating(self, member, which):
        return self.tables[which].get(member, {}).get("rating", RATING_START) if member else RATING_START

    def snapshot(self, members, now):
        """{"mode", "ratings": {"<member>": rating}} for a room opening now
        (A8), or None in off."""
        which = self.mode_at(now)
        if which == "off":
            return None
        return {"mode": which, "ratings": {str(m): self.rating(m, which) for m in sorted(set(members)) if m}}

    def rate(self, rec, snap, now):
        """Rate one settled record (OmpStore.settle, before it is appended)
        from its room's snapshot. In "on" the record gets rating_before /
        after for the rated rows and ranked = the quorum; in "shadow" the
        record stays unranked and a line goes to shadow_log. Returns a log
        note ("" when nothing was rated)."""
        which = snap.get("mode")
        if self.mode == "off" or which not in ("shadow", "on"):
            return ""
        table = self.tables[which]
        ratings = {int(m): v for m, v in (snap.get("ratings") or {}).items()}
        quorum, changes = rating_changes(rec["players"], ratings)
        rows = []
        for i, change in changes.items():
            p = rec["players"][i]
            m = p.get("member") or 0
            if not m:
                continue                # a guest counts as an opponent, never stored
            e = table.setdefault(m, {"rating": RATING_START, "races": 0, "finished": 0, "updated": None})
            before = e["rating"]
            after = max(before + change, RATING_FLOOR)
            e.update(rating=after, races=e["races"] + 1, updated=int(now),
                     finished=e["finished"] + (p["status"] == "finished"))
            rows.append((m, before, after))
            if which == "on":
                p["rating_before"], p["rating_after"] = before, after
        if not rows:
            return ""
        if which == "on":
            rec["ranked"] = quorum
            self.board = None
        elif self.shadow_log:
            os.makedirs(os.path.dirname(os.path.abspath(self.shadow_log)), exist_ok=True)
            line = {"id": rec["id"], "settled": rec["settled"], "n": len(rec["players"]), "quorum": quorum,
                    "players": [{"member": m, "before": b, "after": a, "change": a - b} for m, b, a in rows]}
            with open(self.shadow_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(line, separators=(",", ":")) + "\n")
        self.write(which, now)
        return ("rated" + (" (shadow)" if which == "shadow" else "") + ("" if quorum else ", leavers only") + ": "
                + ", ".join(f"{m} {b}->{a}" for m, b, a in rows))

    def leaderboard(self):
        """[(member, entry)] of the "on" table, best first (rating, then
        more races, then the lower member id)."""
        if self.board is None:
            self.board = sorted(self.tables["on"].items(), key=lambda x: (-x[1]["rating"], -x[1]["races"], x[0]))
        return self.board


OMP_RATINGS = [OmpRatings()]            # replaced by main() with the file-backed one (off by default)


def lb_banned_report(banned, members_path, usernames_path, times_path, ghosts_dir=None, results_path=None,
                     prize_sent_path=None):
    """--lb-banned-report (v5.80, #607): what each banned member has
    stored, read straight from the files (nothing is written, so it is
    safe while CC runs). banned: [(member, why)]. No player keys, no IPs."""
    def load(path, default):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError, TypeError):
            return default
    key_of = {m: k for k, m in load(members_path, {}).get("members", {}).items()}
    usernames = load(usernames_path, {})
    times = load(times_path, {})
    ghosts = load(os.path.join(ghosts_dir, "index.json"), {}).get("ghosts", {}) if ghosts_dir else {}
    sent = load(prize_sent_path, {}) if prize_sent_path else {}
    races = {}
    if results_path:
        try:
            with open(results_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    for p in rec.get("players", []):
                        m = omp_member(p.get("member") or 0)
                        races[m] = races.get(m, 0) + 1
        except OSError:
            pass
    if not banned:
        return "lb-banned report: nobody banned"
    out = [f"lb-banned report: {len(banned)} member(s)"]
    for m, why in banned:
        k = key_of.get(m)
        ev = sorted(int(e) for e, rows in times.items() if k and k in rows and str(e).isdigit())
        gh = sum(1 for g in ghosts if g.split("_")[0] == str(m))
        ps = sent.get(str(m), {})
        paid = sorted(int(e) for e, t in ps.items() if isinstance(t, int) and t > 0)
        held = sorted(int(e) for e, t in ps.items() if isinstance(t, int) and t < 0)
        out.append(f"member {m} ({why}): " + (usernames.get(k) or "no username" if k else "unknown member")
                   + f"; {len(ev)} stored time(s)" + (f" {ev}" if ev else "") + f"; {gh} ghost(s)"
                   + f"; {races.get(m, 0)} OMP race(s); prizes sent {paid or 'none'}"
                   + (f", withheld {held}" if held else ""))
    return "\n".join(out)


def held_report(times_path, members_path, usernames_path, ghosts_dir=None, banned=(), testers=(), blocked=()):
    """--held-report (v5.84, #606): every held time, read straight from the
    files (safe while CC runs), with the field it was held against and the
    lines that approve or reject it. The field: the other players' times,
    a held one as its previous best, banned / blocked / tester members left
    out. No player keys, no IPs."""
    def load(path, default):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError, TypeError):
            return default
    members = load(members_path, {}).get("members", {})
    usernames = load(usernames_path, {})
    data = load(times_path, {})
    ghosts = load(os.path.join(ghosts_dir, "index.json"), {}).get("ghosts", {}) if ghosts_dir else {}
    out_of_field = set(banned) | set(testers) | set(blocked)
    lines = []
    for ev, rows in sorted(data.items(), key=lambda x: str(x[0])):
        if not isinstance(rows, dict):
            continue
        for k, e in rows.items():
            if not isinstance(e, dict) or not e.get("held"):
                continue
            field = []
            for k2, e2 in rows.items():
                if k2 == k or not isinstance(e2, dict) or members.get(k2) in out_of_field:
                    continue
                v = e2.get("prev") if e2.get("held") else e2
                if v and isinstance(v.get("time_ms"), int):
                    field.append((v["time_ms"], v.get("car"), v.get("pr")))
            m = members.get(k, 0)
            prs = [p for _t, c, p in field if c == e.get("car") and isinstance(p, (int, float))]
            g = ghosts.get(f"{m}_{ev}")
            when = datetime.datetime.fromtimestamp(e.get("held_at") or 0, datetime.timezone.utc)
            lines.append(
                f"member {m} {usernames.get(k) or '(no username)'}, event {ev}: {e['time_ms'] / 1000:.3f} s, "
                f"car {e.get('car')} PR {e.get('pr')}, held {when:%Y-%m-%d %H:%M} UTC: "
                + "; ".join(HOLD_REASONS.get(c, c) for c in e["held"])
                + f"\n  field: {len(field)} other time(s)"
                + (f", fastest {min(t for t, _c, _p in field) / 1000:.3f} s" if field else "")
                + (f", same car PR {min(prs)}-{max(prs)}" if prs else "")
                + (f"; previous best {e['prev']['time_ms'] / 1000:.3f} s" if e.get("prev") else ""))
            lines[-1] += (f"; ghost {g['lap_ms'] / 1000:.3f} s" if g else "; no ghost")
            lines[-1] += (f"\n  approve member {m} event {ev} time {e['time_ms']}"
                          f"\n  reject member {m} event {ev} time {e['time_ms']}")
    if not lines:
        return "held report: nothing held"
    return f"held report: {len(lines)} held time(s) (add a line to lb-banned.txt to approve or reject)\n" \
        + "\n".join(lines)


FLOOR_SHARE = 0.9               # v5.86 (#606): suggested floor = this x the fastest trusted lap
FLOOR_MIN_TIMES = 5             # v5.86: trusted times a track needs before a floor is suggested


def floors_suggest(times_path, members_path, ghosts_dir, event_index, results_path, out_path,
                   left_out=(), share=FLOOR_SHARE, min_times=FLOOR_MIN_TIMES):
    """--floors-suggest OUT (v5.86, #606 phase 2): write a suggested
    --lb-floors table to OUT, read straight from the stores (nothing they
    hold is changed). Time Trial ("tt", by track name): every stored time
    that is not held, whose member is not in left_out (banned, blocked,
    testers) and that has a ghost of exactly that lap; floor = share x the
    fastest, for a track with min_times such times. OMP ("omp", by track
    id): per-lap times (time / laps) of finished players in public rooms
    with 2+ finishers, not disputed, not a forfeit; the same rule. OUT also
    names the fastest time behind each floor, for the admin's check. Returns
    a summary line."""
    def load(path, default):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError, TypeError):
            return default
    members = load(members_path, {}).get("members", {})
    data = load(times_path, {})
    ghosts = load(os.path.join(ghosts_dir, "index.json"), {}).get("ghosts", {}) if ghosts_dir else {}
    left_out = set(left_out)
    track_of = {}
    with open(event_index, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                track_of[int(r["event_id"])] = (r.get("track") or "").strip()
            except (KeyError, ValueError, TypeError):
                continue
    tt = {}                     # track -> [(time, member, event)]
    for ev, rows in data.items():
        if not str(ev).isdigit() or int(ev) in IGNORED_EVENTS or not isinstance(rows, dict):
            continue
        track = track_of.get(int(ev))
        for k, e in rows.items():
            m = members.get(k, 0)
            if not track or not isinstance(e, dict) or e.get("held") or m in left_out:
                continue
            g = ghosts.get(f"{m}_{ev}")
            if g and g.get("lap_ms") == e.get("time_ms"):
                tt.setdefault(track, []).append((e["time_ms"], m, int(ev)))
    omp = {}                    # track id -> [(per-lap ms, member, match id)]
    if results_path:
        try:
            with open(results_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    if rec.get("private") or rec.get("selector") or rec.get("disputed") or omp_forfeit(rec):
                        continue
                    fin = [p for p in rec.get("players", []) if p.get("status") == "finished" and p.get("time_ms")]
                    if len(fin) < 2:
                        continue
                    laps = max(int(rec.get("laps") or 1), 1)
                    for p in fin:
                        if p.get("member") not in left_out:
                            omp.setdefault(rec.get("track"), []).append((p["time_ms"] // laps, p.get("member"), rec.get("id")))
        except OSError:
            pass
    rows, skipped = [], 0
    for kind, table in (("tt", tt), ("omp", omp)):
        for key, xs in sorted(table.items(), key=lambda kv: str(kv[0])):
            if len(xs) < min_times:
                skipped += 1
                continue
            best = min(xs)
            rows.append(dict(kind=kind, key=key, floor_ms=int(best[0] * share), fastest_ms=best[0],
                             fastest_member=best[1], fastest_at=best[2], times=len(xs)))
    tmp = out_path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["kind", "key", "floor_ms", "fastest_ms", "fastest_member", "fastest_at", "times"])
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, out_path)
    return (f"floors suggested: {sum(r['kind'] == 'tt' for r in rows)} Time Trial track(s), "
            f"{sum(r['kind'] == 'omp' for r in rows)} OMP track(s) in {out_path}; "
            f"{skipped} track(s) with fewer than {min_times} trusted times left out")


def ratings_report(path, log_path=None, name=str, n=10):
    """--ratings-report: the top and bottom n of a ratings file and the n
    largest swings of its room log (shadow week check, #263)."""
    data = OmpRatings(path).tables["on"]
    rows = sorted(data.items(), key=lambda x: (-x[1]["rating"], -x[1]["races"], x[0]))
    out = [f"{path}: {len(rows)} rated players"]

    def line(i, m, e):
        return (f"  {i:3}. {name(m)} ({m}): {e['rating']}, {e['races']} races, {e['finished']} finished")
    out.append(f"top {min(n, len(rows))}:")
    out += [line(i, m, e) for i, (m, e) in enumerate(rows[:n], 1)]
    if len(rows) > n:
        out.append(f"bottom {min(n, len(rows) - n)}:")
        start = max(n, len(rows) - n)
        out += [line(i, m, e) for i, (m, e) in enumerate(rows[start:], start + 1)]
    if log_path:
        swings = []
        try:
            with open(log_path, encoding="utf-8") as f:
                for text in f:
                    try:
                        room = json.loads(text)
                        swings += [(abs(p["change"]), p["change"], p["member"], room["id"], room["quorum"])
                                   for p in room["players"]]
                    except (ValueError, KeyError, TypeError):
                        continue
        except FileNotFoundError:
            pass
        swings.sort(key=lambda x: (-x[0], x[3]))
        out.append(f"largest swings ({log_path}):")
        out += [f"  {c:+d} {name(m)} ({m}), room {rid}" + ("" if q else " (leaver, no quorum)")
                for _a, c, m, rid, q in swings[:n]]
    return "\n".join(out)


def invite_news_reply(member, owner_name, now):
    """10748 reply with one popup item per pending invite for member (v5.56,
    #427): type 2 (content, VIEW CONTENT), flag_a0 1 (popup at main-menu
    load), flag_a1 1, string 4 = title, string 5 = text; the game shows each
    id once. None when there is none (no answer, as before)."""
    items, info = invite_news_items(member, owner_name, now)
    return (news_payload(NEWS_CATEGORIES, items), info) if items else (None, "")


def invite_news_items(member, owner_name, now):
    """The invite popup items for member (v5.85: split out of
    invite_news_reply so 10748 can merge them with --news); ([], "") when
    there is none."""
    inv = OMP_INVITES[0].pending(member, now)
    if not inv:
        return [], ""
    items = [popup_item(INVITE_NEWS_BASE + r["room"] % (1 << 30), r["created"], r["expires"],
                        f"{owner_name(r['owner'])} invited you to race",
                        "Open prr3.devel60.net > Invites to join (15 min)") for r in inv]
    return items, f"invite notice: {len(inv)} invite(s)"


NEWS_CATEGORIES = [("PRR", 0, "PRR")]   # the category every PRR popup item names


def popup_item(item_id, start, end, title, text):
    """One 10748 news item shown as a one-time popup at main-menu load
    (v5.56 layout, analysis/online-multiplayer.md "News test results"):
    type 2 (content, VIEW CONTENT), flag 1, string 4 = title, string 5 =
    text, category "PRR", flag_a0 1 (popup), flag_a1 1, no deep link (the
    popup's button never runs it)."""
    out = blob.u32(item_id, 2, 1, start, end)
    out += b"".join(blob.string(x) for x in ("", "", "", title, text))
    return out + blob.u32(0) + blob.string("PRR") + blob.u32(1, 1) + blob.string("") + blob.string("")


def news_payload(categories, items):
    """A 10748 reply: categories (str, u32, str) then the items' bytes."""
    out = blob.u32(len(categories))
    for a, n, b in categories:
        out += blob.string(str(a)) + blob.u32(int(n)) + blob.string(str(b))
    return out + blob.u32(len(items)) + b"".join(items)


class OmpStore:
    """Online multiplayer matches and their results (v5.47, issue #360;
    spec #359 "Stored match record"). Replaces v5.19's memory-only
    OMP_MATCHES.

    open_path (--omp-matches, data/rr3-omp-matches.json): open matches only,
    rewritten on every change and reloaded at start, so a restart keeps
    them. results_path (--omp-results, data/rr3-omp-results.jsonl): one
    settled record per line, appended once, never rewritten; loaded at
    start and indexed by id, by member and by UTC day. None = memory only.

    An open match: {"id", "match", "week", "track", "laps", "started",
    "starters": [[value, car or null], ...], "first_report": t or null,
    "reports": {"<sender value>": [[value, status, time ms, flag], ...]}}
    (v5.67, #521: the 2nd value is the phone's status code; v5.47-v5.66
    called it a position).
    "match" is the id the phones got; "id" the record id (the same unless
    it was already used). One report per sender (the newest kept, in the
    order senders first reported). The caller holds the server lock."""

    def __init__(self, open_path=None, results_path=None, server_key=None, log=print, ratings=None):
        self.open_path, self.results_path = open_path, results_path
        self.ratings_obj = ratings      # OmpRatings (v5.79, #263); None = OMP_RATINGS[0]
        self.server_key = server_key or b""
        self.log = log
        self.open = {}                  # "week:v1,v2,.." -> open match
        self.recent = {}                # same key -> (match, track, laps, started, settled, reports) after settling
        self.records = []               # settled records, oldest first
        self.by_id = {}                 # record id -> index in records
        self.by_member = {}             # member -> [index in records], oldest first
        self.by_day = {}                # "YYYY-MM-DD" (settled, UTC) -> rooms settled that day
        self.pids = {}                  # pid -> member, for members in the results
        # v5.71 (#542): Top 10 counts {kind: {member: [value, record index when reached]}}
        self.top_counts = {"wins": {}, "podiums": {}, "races": {}}
        self.top_races, self.top_updated, self.top_cache = 0, None, None
        self.load()

    # --- files ---------------------------------------------------------------
    def load(self):
        if self.results_path:
            try:
                with open(self.results_path, encoding="utf-8") as f:
                    for n, line in enumerate(f, 1):
                        if not line.strip():
                            continue
                        try:
                            rec = json.loads(line)
                            int(rec["id"]), list(rec["players"])
                        except (ValueError, KeyError, TypeError):
                            self.log(f"omp results {self.results_path}: line {n} not read, skipped")
                            continue
                        if rec["id"] in self.by_id:
                            self.log(f"omp results {self.results_path}: line {n} repeats id {rec['id']}, skipped")
                            continue
                        self.index(rec)
            except FileNotFoundError:
                pass
        if self.open_path:
            try:
                with open(self.open_path, encoding="utf-8") as f:
                    data = json.load(f)
                self.open = {k: m for k, m in data.items() if isinstance(m, dict) and "id" in m}
            except FileNotFoundError:
                pass
            except (OSError, ValueError, AttributeError) as e:
                self.log(f"omp matches {self.open_path}: not read ({e}); starting with no open matches")

    def save_open(self):
        if not self.open_path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.open_path)), exist_ok=True)
        tmp = self.open_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.open, f, indent=1)
        os.replace(tmp, self.open_path)

    def append(self, rec):
        if self.results_path:
            os.makedirs(os.path.dirname(os.path.abspath(self.results_path)), exist_ok=True)
            with open(self.results_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        self.index(rec)

    def index(self, rec):
        i = len(self.records)
        self.records.append(rec)
        self.by_id[rec["id"]] = i
        day = utc_date(rec.get("settled") or rec.get("started") or 0)
        self.by_day[day] = self.by_day.get(day, 0) + 1
        for m in sorted({omp_member(p.get("member") or 0) for p in rec["players"]} - {0}):
            self.by_member.setdefault(m, []).append(i)
            self.pids[self.pid(m)] = m
        self.count_top(rec, i)

    @staticmethod
    def valid_finishers(rec):
        """The players of a settled record who count as finishers (v5.82,
        #360): none for an invite (v5.56) or Race Selector (v5.60) room or
        a room of fewer than 2 starters; else those with status finished
        and a time omp_time_ok takes (so a record stored before v5.82 with
        an impossible time doesn't count), in place order."""
        if rec.get("private") or rec.get("selector") or len(rec["players"]) < 2:
            return []
        fin = [p for p in rec["players"]
               if p.get("status") == "finished" and omp_time_ok(p.get("time_ms"), rec.get("laps"), rec.get("track"))]
        return sorted(fin, key=lambda p: p.get("position", 99))

    def count_top(self, rec, i):
        """Top 10 counts (v5.71, #542 D5; v5.82, #360): every valid finisher
        (valid_finishers) with a member: races +1 (a solo finisher too, as
        races_finished counts it); with 2+ valid finishers also place 1 = a
        win and 1-3 = a podium, placed among the valid finishers. Ties:
        whoever reached the value first ranks higher."""
        fin = self.valid_finishers(rec)
        if not fin:
            return
        self.top_races += 1
        self.top_updated = rec.get("settled") or rec.get("started")
        self.top_cache = None
        for place, p in enumerate(fin, 1):
            m = omp_member(p.get("member") or 0)
            if not m:
                continue
            kinds = ["races"] + (["podiums"] if len(fin) >= 2 and place <= 3 else []) \
                + (["wins"] if len(fin) >= 2 and place == 1 else [])
            for kind in kinds:
                c = self.top_counts[kind].setdefault(m, [0, i])
                c[0], c[1] = c[0] + 1, i

    def top(self, skip=None):
        """{kind: [(member, value)] x TOP_N}, sorted once per change. skip
        (v5.80, #607): members left out (banned), the places below move up."""
        if self.top_cache is None:
            self.top_full = {k: [(m, v) for m, (v, _i) in sorted(c.items(), key=lambda x: (-x[1][0], x[1][1]))]
                             for k, c in self.top_counts.items()}
            self.top_cache = {k: rows[:TOP_N] for k, rows in self.top_full.items()}
        if skip is None:
            return self.top_cache
        return {k: [(m, v) for m, v in rows if not skip(m)][:TOP_N] for k, rows in self.top_full.items()}

    @property
    def ratings(self):
        return self.ratings_obj or OMP_RATINGS[0]

    def snap(self, m, members, now):
        """v5.79 (#263 item 1, A8): the members' ratings when the room
        opens, from the mode in force; none for an invite or Race Selector
        room (unrated, decision 6) or with --ratings off."""
        if m.get("private") or m.get("selector"):
            return m
        s = self.ratings.snapshot(members, now)
        if s is not None:
            m["rating"] = s
        return m

    # --- ids -----------------------------------------------------------------
    def pid(self, member):
        """Public player id (#359 R1): first 12 hex of HMAC-SHA256(server
        key, b"pid" + u32 member). Computed, never stored."""
        return hmac.new(self.server_key, b"pid" + struct.pack("<I", member), hashlib.sha256).hexdigest()[:12]

    def free_id(self, match):
        used = {m["id"] for m in self.open.values()}
        i = match
        while i in self.by_id or i in used:
            i = i % 0x7FFFFFFF + 1
        return i

    @staticmethod
    def key(week, ids):
        return f"{week}:" + ",".join(map(str, sorted(ids)))

    # --- matches -------------------------------------------------------------
    def known(self, week, ids):
        """(match id, track, laps, seen StartMatch) the phones of this
        roster got, or None."""
        k = self.key(week, ids)
        m = self.open.get(k)
        if m:
            return m["match"], m["track"], m["laps"], any(c is not None for _v, c in m["starters"])
        r = self.recent.get(k)
        return r[:3] + (True,) if r else None

    def started(self, week, rows, match, track, laps, now, sender=None, member=None, selector=False):
        """StartMatch rows [(value, car)]: open the match unless this roster
        already has it open (the room's other phones). A request whose own
        slot isn't the asking member is not stored (member None = not
        checked). Returns a note for the log ("" when nothing to say)."""
        if member is not None and sender is not None and sender != member and sender < GUEST_VALUE:
            return f"not stored: sender {sender} is not member {member}"
        if member is not None and sender is None:
            return "not stored: sender slot outside the roster"
        k = self.key(week, [v for v, _c in rows])
        note = ""
        self.settle_due(now)
        old = self.open.get(k)
        if old and old["match"] == match:
            return ""                   # another phone of the same room
        r = self.recent.get(k)
        if r and r[0] == match:
            return "already settled"
        if old:                         # the same players' next race: the last one is over
            note = self.settle(k, now, "timeout")
        if len(self.open) >= MATCH_MAX:
            oldest = min(self.open, key=lambda x: self.open[x]["started"])
            self.log(f"omp: {MATCH_MAX} open matches, settling the oldest ({self.open[oldest]['id']}) early")
            self.settle(oldest, now, "timeout")
        members = sorted(v for v, _c in rows if 0 < v < GUEST_VALUE)
        self.open[k] = self.snap(dict(id=self.free_id(match), match=match, week=week, track=track, laps=laps,
                                      started=int(now), starters=sorted([v, c] for v, c in rows),
                                      first_report=None, reports={},
                                      league=OMP_LEAGUES[0].served(members[0]) if members else 1,   # v5.48 (#264)
                                      private=OMP_INVITES[0].is_private(members, now),               # v5.56 (#427)
                                      selector=selector, start_seen=True),                           # v5.60 (#469); v5.84
                                 members, now)                                                       # v5.79 (#263)
        self.save_open()
        return note

    def report(self, week, players, match, track, laps, now, sender=None, member=None):
        """One FinishedMatch: players [(value, status, time ms, flag)],
        sender = the sending phone's own player value. Kept as that
        sender's report (the newest replaces an older one). A report for
        a roster with no open match opens one (no StartMatch seen, cars
        unknown). Settles the match when every starter has reported.
        Returns a note for the log."""
        if sender is None:
            return "not stored: sender slot outside the roster"
        if member is not None and sender != member and sender < GUEST_VALUE:
            return f"not stored: sender {sender} is not member {member}"
        k = self.key(week, [q[0] for q in players])
        self.settle_due(now)
        m = self.open.get(k)
        if m is None:
            r = self.recent.get(k)
            if r and r[0] == match:
                return f"late report for settled match {r[0]}, not stored"
            if len(self.open) >= MATCH_MAX:
                oldest = min(self.open, key=lambda x: self.open[x]["started"])
                self.settle(oldest, now, "timeout")
            members = sorted(q[0] for q in players if 0 < q[0] < GUEST_VALUE)
            m = self.open[k] = self.snap(dict(id=self.free_id(match), match=match, week=week, track=track,
                                              laps=laps, started=int(now),
                                              starters=sorted([q[0], None] for q in players),
                                              first_report=None, reports={},
                                              league=OMP_LEAGUES[0].served(members[0]) if members else 1,
                                              private=OMP_INVITES[0].is_private(members, now),     # v5.56
                                              selector=OMP_SELECTOR[0].room_for(members, now) is not None),
                                         members, now)                                     # v5.79 (#263)
        if m["first_report"] is None and any(omp_row_status(q[1], q[2], q[3], m["laps"], m.get("track"))[0] == "finished"
                                             for q in players):
            m["first_report"] = int(now)    # v5.82 (#360): the first report with a finished row
        m["reports"][str(sender)] = [list(q) for q in players]
        if any(q[0] == sender and omp_row_status(q[1], q[2], q[3], m["laps"], m.get("track"))[0] == "finished" for q in players):
            m.setdefault("report_at", {}).setdefault(str(sender), int(now))   # v5.84 (#606 O3): own finish seen
        starters = {v for v, _c in m["starters"]}
        if starters <= {int(s) for s in m["reports"]}:
            return self.settle(k, now, "all")
        self.save_open()
        return f"report {len(m['reports'])} of {len(starters)} kept"

    def reports_of(self, week, ids, match):
        """The kept reports {"<sender>": rows} of this roster's match with
        this match id, open or settled in the last MATCH_KEEP_S (memory
        only), else {} (v5.67, #521: the reply takes a player's own report
        from here; phones send FinishedMatch 2-3 times)."""
        k = self.key(week, ids)
        m = self.open.get(k)
        if m and m["match"] == match:
            return dict(m["reports"])
        r = self.recent.get(k)
        return dict(r[5]) if r and r[0] == match else {}

    def settle_due(self, now):
        """Settle every open match past its deadline (any request or the
        timer tick calls this). Returns how many."""
        due = [k for k, m in self.open.items()
               if now >= min(m["started"] + settle_cap(m.get("laps")),
                             (m["first_report"] + SETTLE_AFTER_S) if m["first_report"] is not None else 1 << 62)]
        for k in due:
            self.log("omp " + self.settle(k, now, "timeout"))
        return len(due)

    def settle(self, k, now, how):
        """Turn open match k into its record and append it (#359). A match
        nobody reported for is dropped (nothing is known about it)."""
        m = self.open.pop(k)
        self.recent[k] = (m["match"], m["track"], m["laps"], m["started"], int(now), m["reports"])
        for x in [x for x, r in self.recent.items() if now - r[4] > MATCH_KEEP_S]:
            del self.recent[x]
        self.save_open()
        if not m["reports"]:
            return f"match {m['id']} dropped: no reports"
        players = []
        for value, car in m["starters"]:
            status, ms, n, code = self.resolve(m, value)
            players.append(dict(member=omp_member(value), car=car, position=0, status=status, time_ms=ms,
                                reports=n, rating_before=None, rating_after=None, value=value, code=code,
                                how=""))
        # v5.67 (#521): the status code decides (2 = left). v5.51's time rule is only a fallback for a
        # code not in OMP_STATUS: such a "finished" player with a shorter time than a status-1 finisher left.
        done = [q for q in players if q["status"] == "finished"]
        for q in done:
            if q["code"] not in OMP_STATUS and any(o["code"] == OMP_ST_FINISHED and o["time_ms"] > q["time_ms"]
                                                   for o in done):
                q["status"], q["time_ms"], q["how"] = "left", None, " (time rule)"
        # v5.67: finished by time (v5.49-v5.66: by the 2nd field, read as a position); then the rest by time
        players.sort(key=lambda q: (q["status"] != "finished",
                                    q["time_ms"] if q["time_ms"] is not None else 1 << 62, q["value"]))
        for q in players:                                     # v5.86 (#606 O1): say why
            own = m["reports"].get(str(q["value"]), [])
            mine = next((r for r in own if r[0] == q["value"]), None)
            if (q["status"] == "dnf" and mine and OMP_STATUS.get(mine[1], "finished") == "finished"
                    and omp_time_ok(mine[2], m["laps"]) and not omp_time_ok(mine[2], m["laps"], m.get("track"))):
                q["how"] = f" (under the track minimum: {mine[2]} ms)"
        disputed = self.disputes(m, players)                 # v5.84 (#606 O2, O3)
        why = {}
        for i, q in enumerate(players):
            q["position"] = i + 1
            why[i] = q["how"] or (f" (status {q['code']})" if q["status"] == "left" else "")
            del q["value"], q["code"], q["how"]
        rec = dict(id=m["id"], week=m["week"], track=m["track"], laps=m["laps"], league=m.get("league"),
                   started=m["started"], settled=int(now), settled_by=how, ranked=False, players=players)
        if m.get("private"):            # v5.56 (#427): an invite group's race, unranked
            rec["private"] = True
        if m.get("selector"):           # v5.60 (#469): a Race Selector P2P race, unranked
            rec["selector"] = True
        if disputed:                    # v5.84 (#606): kept, logged, never rated
            rec["disputed"] = disputed
        rated = ""
        if m.get("rating") and not m.get("private") and not m.get("selector") and not disputed:     # v5.79 (#263)
            rated = self.ratings.rate(rec, m["rating"], now)
        self.append(rec)
        return (f"match {rec['id']} settled ({how}): "
                + ", ".join(f"{q['member'] or 'guest'} {q['position']} {q['status']}{why[i]}"
                            for i, q in enumerate(players)) + (f"; {rated}" if rated else "")
                + "".join(f"; disputed member {d['member'] or 'guest'}: {d['why']}" for d in disputed))

    def disputes(self, m, players):
        """v5.84 (#606): [{"member", "why"}] for the finishers of open match
        m whose result doesn't hold up. O2: their own reported time differs
        from a time another phone reported for them by more than
        OMP_AGREE_MS. O3 (only when StartMatch was seen): their own finish
        report came more than OMP_LATE_S after start + their time (slow
        motion), or before start + their time - OMP_EARLY_S (impossible).
        players: settle's rows, still with "value"."""
        out = []
        at = m.get("report_at", {})
        fin = [q for q in players if q["status"] == "finished"]
        if len(players) >= 2 and len(fin) == 1:     # a forfeit win (O4): its time means nothing, nothing to dispute
            return out
        for q in players:
            if q["status"] != "finished" or q["time_ms"] is None:
                continue
            v, ms, why = q["value"], q["time_ms"], []
            own = m["reports"].get(str(v))
            if own is not None:
                for sender, rows in m["reports"].items():
                    if int(sender) == v:
                        continue
                    for rv, code, rms, flag in rows:
                        st, t = omp_row_status(code, rms, flag, m["laps"], m.get("track"))
                        if rv == v and st == "finished" and abs(t - ms) > OMP_AGREE_MS:
                            why.append(f"own {ms} ms, {sender} saw {t} ms")
            if m.get("start_seen") and str(v) in at:
                elapsed = at[str(v)] - m["started"]
                if elapsed > ms / 1000 + OMP_LATE_S:
                    why.append(f"finish reported {elapsed} s after start for a {ms // 1000} s race (slow motion?)")
                elif elapsed < ms / 1000 - OMP_EARLY_S:
                    why.append(f"finish reported {elapsed} s after start for a {ms // 1000} s race (too early)")
            if why:
                out.append({"member": q["member"], "why": "; ".join(why)})
        return out

    def resolve(self, m, value):
        """(status, time ms, reports agreeing, status code) for one
        starter: their own report sets it; else the most common value among
        the phones that saw them (a tie: the first report's); nobody = dnf,
        0 reports, code 0. The code (v5.67, #521) feeds settle's fallback."""
        seen = []                       # (status, time, code) per report, in report order
        for sender, rows in m["reports"].items():
            for v, code, ms, flag in rows:
                if v == value:
                    st = omp_row_status(code, ms, flag, m["laps"], m.get("track"))
                    seen.append((int(sender) == value, st + (code if st[0] != "dnf" else 0,)))
        if not seen:
            return "dnf", None, 0, 0
        own = [s for is_own, s in seen if is_own]
        values = [s for _o, s in seen]
        if own:
            pick = own[0]
        else:
            counts = {}
            for s in values:
                counts[s] = counts.get(s, 0) + 1
            best = max(counts.values())
            pick = next(s for s in values if counts[s] == best)
        return pick[0], pick[1], values.count(pick), pick[2]

    # --- reading -------------------------------------------------------------
    def races_finished(self, member):
        """Settled rooms where member is a valid finisher (v5.82, #360:
        valid_finishers, a solo finisher too; v5.51-v5.81: only rooms with
        2+ finishers; v5.47-v5.50: 2 starters; #258 B5, leagues #264)."""
        return sum(1 for i in self.by_member.get(member, ())
                   if any(p.get("member") == member for p in self.valid_finishers(self.records[i])))

    def settled_on(self, day):
        """Rooms settled on UTC day "YYYY-MM-DD" (#374 races_today)."""
        return self.by_day.get(day, 0)

    def page(self, indexes, before=None, limit=20):
        """Records at indexes (ascending; None = all), newest first, those
        older than record id before (None = from the newest). Returns (records, id for the next page or None)."""
        if indexes is None:             # every record
            indexes = range(len(self.records))
        end = len(indexes)
        if before is not None:
            if before not in self.by_id:
                return [], None
            end = bisect.bisect_left(indexes, self.by_id[before])
        start = max(0, end - limit)
        out = [self.records[i] for i in reversed(indexes[start:end])]
        return out, (out[-1]["id"] if start > 0 and out else None)


OMP_STORE = [OmpStore()]                # replaced by main() with the file-backed store


def track_names(cfg):
    """{track id: name} from the OMP schedule's races (every event), for
    the site (v5.47, #360): the name without its "(file)" part. The game
    data holds no other id -> name table the server can read."""
    out = {}
    for ev in ([cfg] + list(cfg.get("_events") or [])) if cfg else []:
        for r in ev.get("races") or []:
            if isinstance(r, dict) and r.get("name") and "track" in r:
                out.setdefault(r["track"], re.sub(r"\s*\(.*\)\s*$", "", str(r["name"])) or str(r["name"]))
    return out


def load_car_names(path):
    """{car id: name} from tables/car-index.csv (v5.47, for the site)."""
    with open(path, newline="") as f:
        return {int(r["car_id"]): r["name"] for r in csv.DictReader(f) if r.get("name")}


def pending_matches_reply(p):
    """10785 (SyncPendingMatches, v5.52) reply, read by 0xf840b8. Request
    (0xf755e4): u32 n, then n u32 match ids (the phone's pending-match list,
    omp+0x6a8). Reply: u32 n, then the ids to erase from that list; we name
    every id asked about, so the list empties. Returns (reply, log text);
    (None, text) for a request too short to read."""
    if len(p) < 4:
        return None, f"PendingMatches request of {len(p)} bytes not read"
    n = struct.unpack_from("<I", p, 0)[0]
    n = min(n, 64, (len(p) - 4) // 4)
    ids = list(struct.unpack_from(f"<{n}I", p, 4))
    return blob.u32(n, *ids), f"OMP PendingMatches: {n} dropped ({', '.join(map(str, ids)) or 'none'})"


def omp_reply_cell(code, ms, laps, track=None):
    """(status, time) sent in a FinishedMatch reply row for a player's
    picked request row (v5.67, #521): status 0 = empty time (0xFFFFFFFF);
    status 1 with no time = empty (status 0); status 1 with a bad time
    (#143) = DNF time 0xFFFFFFFE; 2 / 3 (left / disconnected: the screen's
    DNF row) and any other code as reported."""
    if code == OMP_ST_NONE or (code == OMP_ST_FINISHED and ms == OMP_NO_TIME):
        return OMP_ST_NONE, OMP_NO_TIME
    if code == OMP_ST_FINISHED and not omp_time_ok(ms, laps, track):     # v5.86: track floor (O1)
        return OMP_ST_FINISHED, OMP_DNF_TIME
    return code, ms


def omp_pick_rows(players, sender, kept):
    """Per player (value, status code, time ms, flag, source) for the reply
    (v5.67, #521; analysis/online-multiplayer.md "Row to send"): the
    player's own report (this request when they are the sender, else one
    kept for the match, OmpStore.reports_of), else the best other report: a finished row
    with a time, then any other non-zero status, then status 0; on a tie
    this request's row, then the earliest kept report's. source = the
    sending player value of the report used (None = this request)."""
    reports = {int(k): {r[0]: tuple(r) for r in rows} for k, rows in kept.items()}
    if sender is not None:
        reports.pop(sender, None)
    out = []
    for q in players:
        v = q[0]
        if v == sender:
            out.append(tuple(q) + (None,))
            continue
        if v in reports.get(v, {}):
            out.append(reports[v][v] + (v,))
            continue
        cands = [(q, None)] + [(rows[v], k) for k, rows in reports.items() if v in rows]
        def best(c):
            code, ms = c[0][1], c[0][2]
            return 0 if code == OMP_ST_FINISHED and ms != OMP_NO_TIME else 1 if code != OMP_ST_NONE else 2
        row, src = min(cands, key=best)      # min keeps the first of equals: this request, then report order
        out.append(tuple(row) + (src,))
    return out


def finished_match_reply(cfg, p, now, store=None, member=None):
    """10532 (FinishedMatch) reply (v5.19, issue #233), read by 0xce8e3c.
    Request (writer 0xce85dc, sent by 0xf7a694 at race end): u32 7469,
    mp+0x11c, mp+0x120, week (omp+0x70), omp+0x4c0, flag, local slot, car
    id, 4 floats, n players, n x (u32 player value, u32 **status** that
    phone gives the player (omp+0x5c8: 1 finished, 2 left, 3 disconnected,
    0 nothing yet), u32 time ms (omp+0x5b0, 0xFFFFFFFF = none yet), u32
    flag [slot+0x7e] (disconnected)), 2 u32 flags. v5.43-v5.66 read the
    status as the position that phone gives the player (#521: wrong; all
    logged rows fit the status); v5.20-v5.42 read the time as the status.
    A player who quits still reports, with status 2 and the time they quit.
    Reply: the StartMatch reply's head (match id, track, laps, field 4 =
    the request's field 3, week, 3 x 0), n player rows and a final flag (0:
    another value takes the local player out of the race list).
    The callback 0xf7b22c moves the OMP state from 5 to 6 when match id,
    track and laps are not 0 (7 otherwise); without a reply the phone
    stays in 5 and its matchmaking screen never retries. In state 6 the
    "verifying results" screen waits for 0xf7e540, which needs rows (the
    first with a non-zero place) and builds the results table from them
    (0x1003c84). Row (v5.67, #521; analysis/online-multiplayer.md
    "FinishedMatch reply rows"): key (the player value), place (1-based:
    the table row, so 1..n, each once, never 0), status (0 empty time, 1
    normal, 2 / 3 DNF row), time ms (0xFFFFFFFF empty, 0xFFFFFFFE DNF),
    rating before, rating after (the rating column; the change shown is
    after - before; the local player's after goes to omp+0x1ac, logged as
    MatchmakingELO). v5.20-v5.66 sent key, place, time, the request's
    status, 0, 1000: the time column showed .001/.002/.003 and the change
    +1000. Status and time per player: omp_pick_rows (own report, else the
    best other) through omp_reply_cell. Place: finished players (status 1
    and a time the server takes) by time, then the others by time.
    Ratings: 1000 / 1000 (change 0) with --ratings off or shadow; on
    (v5.79, #263) the player's stored rating as both (change 0: the room
    is rated at settle, after this reply); with --omp-rating-test
    (v5.43; before / after since v5.67) player 0 gets 1217 / 1234 (+17),
    player 1 996 / 987 (-9), others 1000 / 1000 + index.
    v5.47 (#360): the report is kept in store (default OMP_STORE) as the
    sender's (rows[local slot]); member = the asking phone's member id
    (None = not checked). The reply never waits for the other phones.
    Returns (reply, log text); (None, text) for a request too short."""
    if len(p) < 52:
        return None, f"FinishedMatch request of {len(p)} bytes not read"
    f3, week = struct.unpack_from("<II", p, 8)
    slot = struct.unpack_from("<I", p, 24)[0]
    n = struct.unpack_from("<I", p, 48)[0]
    n = min(n, 43, (len(p) - 52) // 16)
    players = [struct.unpack_from("<4I", p, 52 + 16 * i) for i in range(n)]   # (value, status, ms, flag)
    ids = sorted(q[0] for q in players)
    store = store or OMP_STORE[0]
    known = store.known(week, ids)
    if known:
        match, track, laps, seen = known
        how = "its StartMatch" if seen else "no StartMatch kept, its first report's race"
    else:                                   # no StartMatch seen (restart): the current race
        ev = omp_event(cfg, now)
        race = ev["races"][omp_current_race(ev, now)]
        track, laps = race["track"], race.get("laps", 3)
        match = zlib.crc32(struct.pack(f"<II{n}I", week, 0xFFFFFFFF, *ids)) & 0x7FFFFFFF or 1
        how = "no StartMatch kept, current race"
    sender_v = players[slot][0] if slot < n else None
    picked = omp_pick_rows(players, sender_v, store.reports_of(week, ids, match))
    cells = [omp_reply_cell(code, ms, laps, track) for _v, code, ms, _f, _s in picked]

    def rank(i):
        st, ms = cells[i]
        done = st == OMP_ST_FINISHED and ms not in (OMP_NO_TIME, OMP_DNF_TIME)
        return (0 if done else 1, ms, i)
    place = [0] * n
    for k, i in enumerate(sorted(range(n), key=rank)):
        place[i] = k + 1

    live = store.ratings.mode_at(now) == "on"

    def ratings(i):
        if not OMP_RATING_TEST[0]:      # v5.79 (#263 item 3, A7): the stored rating, change 0, never held
            r = store.ratings.rating(omp_member(players[i][0]), "on") if live else OMP_RATING
            return r, r
        return {0: (1217, 1234), 1: (996, 987)}.get(i, (1000, 1000 + i))
    rows = b"".join(blob.u32(v, place[i], *cells[i], *ratings(i)) for i, (v, *_r) in enumerate(players))
    out = blob.u32(match, track, laps, f3, week, 0, 0, 0, n) + rows + blob.u32(0)
    sender = f"slot {slot}" + (f" = {sender_v}" if slot < n else "")

    def shown(i):
        v, code, ms, fl = players[i]
        st, sms = cells[i]
        src = picked[i][4]
        extra = f"; sent status {st}, {'-' if sms == OMP_NO_TIME else 'DNF' if sms == OMP_DNF_TIME else sms}" \
            + (f" from {src}'s report" if src is not None else "") \
            if (st, sms) != (code, ms) else ""
        return f"{v}: {place[i]} (status {code}, {'-' if ms == OMP_NO_TIME else ms} ms, flag {fl}{extra})"
    places = ", ".join(shown(i) for i in range(n))
    test = "; rating test" if OMP_RATING_TEST[0] else ""
    note = store.report(week, players, match, track, laps, now, sender_v, member)
    return out, (f"OMP FinishedMatch: match {match}, track {track}, laps {laps} ({how}); from {sender}; "
                 f"{places}{test}; {note}")


def top_rows(rows, me, n=LB_ROWS):
    """The n fastest rows, plus the asking player's own row (index me) at
    the end when it is not among them. Returns the rows and me's new index."""
    if len(rows) <= n:
        return rows, me
    if me >= n:
        return rows[:n] + [rows[me]], n
    return rows[:n], me


# --news-test (v5.55, #427 R1): the news room reply (10748) from a JSON test file.
NEWS_TEST = [None]              # path of the test file, or None
NEWS_ITEM_KEYS = ("id", "type", "flag", "start", "end", "strings", "number", "category",
                  "flag_a0", "flag_a1", "link", "last")


def news_reply(member, path, now=None):
    """10748 reply (reader 0x118c94c; analysis/online-multiplayer.md): u32
    category count, per category str a (matched by items), u32, str b; u32
    item count; per item u32 id, u32 type, u32 flag 0/1, u32 start, u32 end
    (Unix s), 5 str (the 4th must not be empty), u32, str category, u32
    flag 0/1, u32 flag 0/1, str deep link (rr3://COMMAND/params), str.
    Strings are u32 length + bytes. start 0 = now - 60, end 0 = now + 1 day.
    Returns (payload or None, log info). The JSON file:
    {"members": [1001], "categories": [["PRR", 0, "PRR"]], "items": [{...}]}
    with the keys of NEWS_ITEM_KEYS; "strings" is a list of 5."""
    cats, items, info = news_test_parts(member, path, now)
    return (news_payload(cats, items) if items is not None else None), info


def news_test_parts(member, path, now=None):
    """news_reply's categories and item bytes (v5.85: so 10748 can merge
    them with --news and the invites). Returns (categories, items, info);
    items None = not answered."""
    now = int(time.time() if now is None else now)
    try:
        d = json.load(open(path))
        if member not in [int(m) for m in d.get("members", [])]:
            return [], None, "news not answered"
        cats = [(str(a), int(n), str(b)) for a, n, b in d.get("categories", [])]
        items = []
        for it in d.get("items", []):
            missing = [k for k in NEWS_ITEM_KEYS if k not in it]
            strs = it.get("strings", [])
            if missing or len(strs) != 5:
                raise ValueError(f"item {it.get('id')}: missing {missing or 'strings x5'}")
            out = blob.u32(int(it["id"]), int(it["type"]), int(it["flag"]) & 1,
                           int(it["start"]) or now - 60, int(it["end"]) or now + 86400)
            out += b"".join(blob.string(str(x)) for x in strs)
            out += blob.u32(int(it["number"])) + blob.string(str(it["category"]))
            out += blob.u32(int(it["flag_a0"]) & 1, int(it["flag_a1"]) & 1)
            out += blob.string(str(it["link"])) + blob.string(str(it["last"]))
            items.append(out)
    except (OSError, ValueError, TypeError, KeyError) as e:
        return [], None, f"news test file not used ({e})"
    return cats, items, f"news test: {len(items)} item(s)"


# --news (v5.85, #644): server-side popup broadcast through 10748.
NEWS = [None]                   # NewsBroadcast, or None
NEWS_ID_BASE = 0x20000000       # sent id = base + file id (clear of EA's ids, test ids, INVITE_NEWS_BASE)
NEWS_ID_MAX = 1 << 28           # file ids 1 .. NEWS_ID_MAX - 1
NEWS_TEXT_MAX = 500             # longest title / text accepted (the game's limit is not known)
NEWS_MESSAGE_KEYS = {"id", "title", "text", "start", "end", "targets", "_note"}
NEWS_TARGET_KEYS = {"build_below", "builds", "not_builds", "members", "not_members", "platform"}
NEWS_ANDROID_BUILD_RE = re.compile(r"PRR b([0-9]{2,})-")


def news_time(v, what):
    """A start/end value: Unix seconds, or an ISO date-time (UTC unless it
    names a zone, e.g. 2026-11-12T00:00Z); None / missing = no limit."""
    if v is None:
        return None
    if isinstance(v, bool):
        raise ValueError(f"{what}: not a time")
    if isinstance(v, (int, float)):
        return int(v)
    t = datetime.datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return int(t.timestamp())


def news_parse(d):
    """The --news file: {"messages": [{id, title, text, start?, end?,
    targets?}]}. Returns the checked messages; ValueError on any problem
    (the whole file is refused, so a typo never sends half a broadcast)."""
    if not isinstance(d, dict) or not isinstance(d.get("messages"), list):
        raise ValueError('needs {"messages": [...]}')
    out, seen = [], set()
    for n, m in enumerate(d["messages"], 1):
        if not isinstance(m, dict):
            raise ValueError(f"message {n}: not an object")
        extra = set(m) - NEWS_MESSAGE_KEYS
        if extra:
            raise ValueError(f"message {n}: unknown key(s) {sorted(extra)}")
        mid = m.get("id")
        if not isinstance(mid, int) or isinstance(mid, bool) or not 0 < mid < NEWS_ID_MAX:
            raise ValueError(f"message {n}: id must be a whole number 1..{NEWS_ID_MAX - 1}")
        if mid in seen:
            raise ValueError(f"message {n}: id {mid} used twice")
        seen.add(mid)
        title, text = m.get("title"), m.get("text", "")
        if not isinstance(title, str) or not title.strip() or not isinstance(text, str):
            raise ValueError(f"message {mid}: needs a title (and text as a string)")
        if len(title) > NEWS_TEXT_MAX or len(text) > NEWS_TEXT_MAX:
            raise ValueError(f"message {mid}: title or text longer than {NEWS_TEXT_MAX}")
        start, end = news_time(m.get("start"), f"message {mid} start"), news_time(m.get("end"), f"message {mid} end")
        if start is not None and end is not None and end <= start:
            raise ValueError(f"message {mid}: end is not after start")
        tg = m.get("targets") or {}
        if not isinstance(tg, dict) or set(tg) - NEWS_TARGET_KEYS:
            raise ValueError(f"message {mid}: targets must be an object with keys {sorted(NEWS_TARGET_KEYS)}")
        t = {}
        if "build_below" in tg:
            if not isinstance(tg["build_below"], int) or isinstance(tg["build_below"], bool):
                raise ValueError(f"message {mid}: build_below must be a build number (56 for b56)")
            t["build_below"] = tg["build_below"]
        for k in ("builds", "not_builds"):
            if k in tg:
                if not isinstance(tg[k], list) or not all(isinstance(x, str) for x in tg[k]):
                    raise ValueError(f"message {mid}: {k} must be a list of build labels")
                t[k] = frozenset(tg[k])
        for k in ("members", "not_members"):
            if k in tg:
                if not isinstance(tg[k], list) or not all(isinstance(x, int) and not isinstance(x, bool)
                                                          for x in tg[k]):
                    raise ValueError(f"message {mid}: {k} must be a list of member ids")
                t[k] = frozenset(tg[k])
        if "platform" in tg:
            if tg["platform"] not in ("android", "ios", "all"):
                raise ValueError(f"message {mid}: platform must be android, ios or all")
            t["platform"] = tg["platform"]
        out.append({"id": mid, "title": title, "text": text, "start": start, "end": end, "targets": t})
    return out


def news_targets(t, member, build, ios):
    """Whether a player matches a message's targets (every key given must
    match). build = the request's label (`PRR b55-beta`, `PRR i01-beta`, or
    "" without one); member None = no member id."""
    build = build or ""
    if "platform" in t and t["platform"] != "all" and (t["platform"] == "ios") != bool(ios):
        return False
    if "build_below" in t:
        m = NEWS_ANDROID_BUILD_RE.match(build)
        if m:
            if int(m.group(1)) >= t["build_below"]:
                return False
        elif build.startswith("PRR i"):
            return False                # an iOS label is never "below" an Android build
    if "builds" in t and build not in t["builds"]:
        return False
    if "not_builds" in t and build in t["not_builds"]:
        return False
    if "members" in t and member not in t["members"]:
        return False
    if "not_members" in t and member in t["not_members"]:
        return False
    return True


class NewsBroadcast:
    """--news FILE (v5.85, #644). The file is checked at most once a second
    and read again when its mtime or size changes (no restart). A missing
    file sends nothing; a bad one is logged once and the last good
    messages stay in use. sent = {id: set of members sent it} since start
    (the server cannot see whether the popup showed)."""

    def __init__(self, path, log=print, clock=time.monotonic):
        self.path, self.log, self.clock = path, log, clock
        self.messages, self.stamp, self.next_check = [], None, 0.0
        self.sent = {}

    def refresh(self):
        now = self.clock()
        if now < self.next_check:
            return
        self.next_check = now + 1.0
        try:
            st = os.stat(self.path)
            stamp = (st.st_mtime_ns, st.st_size)
        except OSError:
            stamp = "missing"
        if stamp == self.stamp:
            return
        self.stamp = stamp
        if stamp == "missing":
            if self.messages:
                self.log(f"news {self.path}: file missing, no messages sent")
            else:
                self.log(f"news {self.path}: no file, no messages")
            self.messages = []
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                msgs = news_parse(json.load(f))
        except (OSError, ValueError) as e:
            self.log(f"news {self.path}: not used ({e}); keeping the last good file "
                     f"({len(self.messages)} message(s))")
            return
        self.messages = msgs
        self.log(f"news {self.path}: {len(msgs)} message(s) " + (", ".join(str(m["id"]) for m in msgs) or "-"))

    def items(self, member, build, ios, now):
        """The popup items for this player now, and a log note."""
        self.refresh()
        now = int(now)
        items, ids = [], []
        for m in self.messages:
            if (m["start"] is not None and now < m["start"]) or (m["end"] is not None and now >= m["end"]):
                continue
            if not news_targets(m["targets"], member, build, ios):
                continue
            items.append(popup_item(NEWS_ID_BASE + m["id"], m["start"] or now - 60, m["end"] or now + 86400,
                                    m["title"], m["text"]))
            ids.append(m["id"])
            if member is not None:
                self.sent.setdefault(m["id"], set()).add(member)
        return items, (f"news: {', '.join(map(str, ids))}" if ids else "")

    def status(self):
        """For /prr/api/status: [{"id", "sent"}] for the current messages."""
        return [{"id": m["id"], "sent": len(self.sent.get(m["id"], ()))} for m in self.messages]


def news_room_reply(member, build, ios, friends, owner_name, now=None):
    """The 10748 answer (v5.85): --news broadcast items, then --news-test
    items, then the OMP invite popups, in one reply (categories without
    duplicates). (None, info) when none of them has an item."""
    now = time.time() if now is None else now
    cats, items, notes = [], [], []

    def add(c, its, info):
        for x in c:
            if x not in cats:
                cats.append(x)
        items.extend(its or [])
        if info:
            notes.append(info)
    if NEWS[0] is not None:
        its, info = NEWS[0].items(member, build, ios, now)
        add(NEWS_CATEGORIES if its else [], its, info)
    if NEWS_TEST[0]:
        add(*news_test_parts(member, NEWS_TEST[0], now))
    if friends:
        its, info = invite_news_items(member, owner_name, now)
        add(NEWS_CATEGORIES if its else [], its, info)
    return (news_payload(cats, items) if items else None), "; ".join(notes)


# --prize-test (v5.39): member id (or "all") -> event ids sent in the 10781 reply.
PRIZE_TEST = {}
PRIZE_ALL = "all"


PRIZE_DAYS = 14                 # v5.76: an ended WTT stays in the prize list this long


class PrizeList:
    """v5.76 (#193): the 10781 prize list from the WTT prize table
    (--prize-events, CSV event_id,start,end,... from rr3_wtt_dates.py
    prizes; re-read when it changes). A member gets the events that ended
    (end <= now) within the last `days`, that they have a stored time in,
    and that they were not sent before. What was sent is kept in `sent_path`
    ({"<member>": {"<event>": unix time sent}}), so each event is listed to a
    member once (#193 open question: the safe choice either way). v5.80
    (#607): a banned member gets an empty list; their due events are kept
    as minus the time (withheld) and never sent. v5.84 (#606): the same for
    a tester; an event whose time is held is left out (not marked sent),
    so it is paid once the time is released or approved."""

    def __init__(self, events_path, sent_path, days=PRIZE_DAYS):
        self.events_path, self.sent_path, self.days = events_path, sent_path, days
        self.mtime, self.events = None, []
        try:
            self.sent = json.load(open(sent_path))
        except FileNotFoundError:
            self.sent = {}
        self.load()

    def load(self):
        """(Re)read the table when its file changed; a bad file keeps the old one."""
        try:
            m = os.stat(self.events_path).st_mtime
        except OSError as e:
            return f"prize table not read ({e})"
        if m == self.mtime:
            return ""
        try:
            with open(self.events_path, newline="") as f:
                ev = [(int(r["event_id"]), int(r["start"]), int(r["end"])) for r in csv.DictReader(f)]
        except (OSError, ValueError, KeyError, TypeError) as e:
            return f"prize table not read ({e})"
        self.mtime, self.events = m, ev
        return f"prize table: {len(ev)} events"

    def window(self, event):
        """v5.84 (#606): (start, end) of a WTT in the table, or None."""
        self.load()
        return next(((st, end) for e, st, end in self.events if e == event), None)

    def due(self, now):
        """Event ids that ended within the last `days`, by end."""
        return [e for e, _s, end in sorted(self.events, key=lambda x: x[2])
                if end <= now and now - end <= self.days * 86400]

    def reply(self, member, key, times, now):
        """10781 reply and log text; None = not answered (no member)."""
        note = self.load()
        if not member or member == NO_MEMBER or not key:
            return None, "prize list not answered (no member)"
        sent = self.sent.get(str(member), {})
        raced = [e for e in self.due(now) if times.rows(e, key)[1] >= 0]
        held = [e for e in raced if times.held(key, e)]     # v5.84 (#606): paid once released, not sent now
        raced = [e for e in raced if e not in held]
        new = [e for e in raced if str(e) not in sent]
        why = times.prize_block(key)                        # v5.84: testers too
        if why:                         # v5.80 (#607): withheld (-time), never paid, even after an unban
            if new:
                sent.update({str(e): -int(now) for e in new})
                self.sent[str(member)] = sent
                self.save()
            return blob.u32(0), f"prize list withheld {new} (banned: {why})" + (f" ({note})" if note else "")
        if new:
            sent.update({str(e): int(now) for e in new})
            self.sent[str(member)] = sent
            self.save()
        info = (f"prize list {new}" + (f", already sent {[e for e in raced if e not in new]}" if len(raced) > len(new) else "")
                + (f", held {held}" if held else ""))
        return blob.u32(len(new), *new), info + (f" ({note})" if note else "")

    def save(self):
        tmp = self.sent_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.sent, f, indent=1, sort_keys=True)
        os.replace(tmp, self.sent_path)


PRIZES = [None]                 # v5.76: the PrizeList, set by main() with --prize-events


def prize_reply(member, key=None, times=None, now=None):
    """10781 reply (reader 0x14ca4fc): u32 count, then u32 event ids. None = no answer.
    --prize-test (v5.39) wins for its members; else the prize table (v5.76)."""
    events = PRIZE_TEST.get(member, PRIZE_TEST.get(PRIZE_ALL))
    if events is not None:
        return blob.u32(len(events), *events), f"prize test: events {events}"
    if PRIZES[0] is not None and times is not None:
        return PRIZES[0].reply(member, key, times, time.time() if now is None else now)
    return None, "prize list not answered"


def parse_prize_test(values):
    """['1001:82870,82877', 'all:82870'] -> {1001: [82870, 82877], 'all': [82870]};
    exits on bad input."""
    out = {}
    for v in values or []:
        try:
            m, evs = v.split(":", 1)
            key = PRIZE_ALL if m.strip().lower() == PRIZE_ALL else int(m)
            out[key] = [int(e) for e in evs.split(",") if e.strip()]
        except ValueError:
            sys.exit(f"--prize-test must be MEMBER:EVENT[,EVENT...], got {v!r}")
    return out


def answer_for(body, times, ghosts=None, host="", schedule=None, plain=None, ip="", shadow=None,
               friends=None, build=None, subsync_list=None, assets=None, saves=None):
    """Store Time Trial results and ghosts. Returns the wrapped reply (None
    when no subsync of the request is answered) and a line for the log.
    plain = the body already unwrapped (the handler does it outside the lock).
    ip = the client's address, for the new-player cap (v5.12). shadow =
    True / False to shadow the player or make them visible (v5.13, from the
    request's APK label), None to leave it as it is. friends = Friends
    (v5.16): keeps the header's player secret, answers 10556 and fills
    10419's rows. saves = CloudSaves (v5.63, #501): answers 10660 and
    10661 and keeps 22's save; v5.64: 10660 status 0, 47 an empty list;
    None = cloud save off (--cloud-save)."""
    if plain is None:
        plain, _ = blob.unwrap(body)
    subs = blob.subsyncs(plain) if subsync_list is None else subsync_list
    key = player_key(plain, times.server_key)
    who = "unknown" if key == "unknown" else f"{key[2:6]}..{key[-4:]}"
    if not times.allow_new(key, ip):
        return None, (f"player {who} new: refused ({times.new_per_ip} new players from this IP "
                      f"in the last {NEW_PLAYER_WINDOW_S // 60} min)")
    if shadow is not None:
        times.set_shadowed(key, shadow)
    times.claim_old(key)
    times.apply_actions()               # v5.84 (#606): approve/reject lines added to --lb-banned
    member = times.member_id(key)
    LIVE_SEEN[0].seen(member, key, time.time())         # v5.68 (#522): a game request
    h = blob.header(plain)
    if key == "unknown":            # v5.34 (#299): which ids does this phone send?
        who += " (ids " + (" ".join(h["shapes"]) or "none") + ")"
    name_note = times.set_username(key, h["username"])
    reset = friends.apply_resets(times.by_member) if friends else ""
    new_secret = friends.set_secret(key, h["secret"]) if friends else False
    differs = friends.note_secret(key, h["secret"]) if friends else ""
    counts = {}
    for t, *_ in subs:
        counts[t] = counts.get(t, 0) + 1
    names = ", ".join(f"{t}" + (f" x{n}" if n > 1 else "") for t, n in counts.items())
    names += f" ({reset})" if reset else ""
    names += f" ({name_note})" if name_note else ""
    names += " (player secret kept)" if new_secret else ""
    names += f" ({differs})" if differs else ""
    answers = {}
    for t, _t2, _z, p in subs:
        if t == 10451:
            queued = blob.race_history(p)
            if times.skip_queued and key not in times.skipped and len(queued) > 1:
                names += f" (skipped {len(queued)} queued result(s))"
                times.skipped.add(key)
            else:
                n = times.add_history(p, key)
                names += f" (stored {n} new best time(s))" if n else ""
                names += "".join(f" ({x})" for x in times.notes)     # v5.84 (#606): held / released
                dropped = sum(r["event"] in IGNORED_EVENTS for r in queued)
                names += f" (dropped {dropped} Race Selector result(s))" if dropped else ""
                unknown = sum(r["event"] not in IGNORED_EVENTS and not times.known(r["event"])
                              for r in queued if r["mode"] == blob.MODE_TIME_TRIAL)
                names += f" (dropped {unknown} result(s) for events not in --events)" if unknown else ""
                refused = [why for r in queued if r["mode"] == blob.MODE_TIME_TRIAL
                           and r["event"] not in IGNORED_EVENTS and times.known(r["event"])
                           for why in [times.result_problem(r)] if why]
                names += (f" (refused {len(refused)} result(s): {refused[0]}"
                          + (", ..." if len(refused) > 1 else "") + ")") if refused else ""
                if times.skip_queued:
                    times.skipped.add(key)
            # Status != 0 makes the game drop uploaded results from its queue.
            answers[10451] = blob.u32(1, 0)
    if any(t == 68 for t, *_ in subs):
        # v5.24 (#242): StatManager sessions. Status != 0 makes the game drop
        # every sent session but the newest (reply 0x1cc80c8), so 68's
        # version line stops naming an old build. The stats are not kept.
        answers[68] = blob.u32(1)
    if ghosts:
        for t, _t2, _z, p in subs:
            if t == 10695:                  # upload slot
                k, url = ghosts.new_slot(key, member, host, build)
                answers.setdefault(10695, []).append(blob.u32(1) + blob.string(k) + blob.string(url))
            elif t == 10694:                # link an uploaded ghost
                ok, info = ghosts.link(p, key)
                answers.setdefault(10694, []).append(blob.u32(ok))
                names += f" ({info})"
                if getattr(ghosts, "last_kept", None):      # v5.84 (#606): T4, a held WTT time's ghost
                    note = times.ghost_arrived(*ghosts.last_kept)
                    names += f" ({note})" if note else ""
            elif t == 10696:                # upload failed: drop its key; the game reads no reply
                ghosts.drop(read_string(p, 0)[0])
                ghosts.save()
                answers[10696] = b""
            elif t == 10476:                # download
                r, info = ghost_reply(p, member, times, ghosts)
                answers.setdefault(10476, []).append(r)
                names += f" ({info})"
    if saves:                               # v5.63 (#501): cloud save, phase (a): backups only
        for t, _t2, _z, p in subs:
            if t not in (10660, 10661, 22, 47):
                continue
            if key == "unknown" or member == NO_MEMBER:
                names += f" (cloud save {t}: no player key, not answered)"
            elif t == 10660:                # upload slot: u32 status (0 = ok, v5.64), str key, str URL
                k, url = saves.new_slot(member, host, build)
                answers.setdefault(10660, []).append(blob.u32(SAVE_SLOT_OK) + blob.string(k) + blob.string(url))
                names += f" (save upload slot {k[:8]}; request {len(p)} bytes)"
            elif t == 10661:                # upload done: bool
                answers.setdefault(10661, []).append(blob.u32(1))
                names += f" ({saves.done(p)})"
            elif t == 47:                   # v5.64: empty list; v5.65: one row for --cloud-save-restore
                r, info = saves.list_reply(member, host, build)
                answers.setdefault(47, []).append(r or SAVE_LIST_EMPTY)
                names += f" ({info})"
            else:                           # 22: corrupt-save report, the save inline
                answers[22] = b""           # the reader (0x1ce8c54) is not traced: empty
                names += f" ({saves.corrupt(member, p)})"
    if schedule and 10536 in counts:
        now = int(time.time())
        league = 1
        if member and member != NO_MEMBER:      # v5.48 (#264): the member's league
            league = OMP_LEAGUES[0].serve(member, OMP_STORE[0].races_finished(member), now)
        ios = is_iphone(h, build)               # v5.66: iPhones' group
        answers[10536] = schedule_reply(schedule, now, league, ios)
        names += (f" ({omp_event_label(schedule, now)}; league {league}" + ("; ios" if ios else "")
                  + f"; {omp_rotation(schedule, now)})")
    if schedule:
        OMP_STORE[0].settle_due(int(time.time()))      # v5.47 (#360): any request settles what is due
        for t, _t2, _z, p in subs:
            if t == 10626:
                r, info = start_match_reply(schedule, p, int(time.time()), member=member)
                if r is not None:
                    answers[10626] = r
                names += f" ({info})"
            elif t == 10532:
                r, info = finished_match_reply(schedule, p, int(time.time()), member=member)
                if r is not None:
                    answers[10532] = r
                names += f" ({info})"
            elif t == 10785:                # v5.52: the phone's pending matches, all dropped
                r, info = pending_matches_reply(p)
                if r is not None:
                    answers[10785] = r
                names += f" ({info})"
    for t, _t2, _z, p in subs:
        if t == 10459:                      # mail
            r, info = mail_reply(p, key, times)
            answers[10459] = r
            names += f" ({info})"
        elif t == 10486:                    # friends leaderboard tab (v5.26)
            r, info = friends_board_reply(p, key, times, friends)
            answers.setdefault(10486, []).append(r)
            names += f" ({info})"
        elif t == 10516:                    # Ghost Challenge rows
            r, info = member_rows_reply(p, key, times)
            answers.setdefault(10516, []).append(r)
            names += f" ({info})"
        elif t == 10419:                    # friends' results per event
            r, info = friends_reply(p, key, times, friends)
            answers.setdefault(10419, []).append(r)
            names += f" ({info})"
        elif t == 10449 and assets and is_iphone(h, build) and not ASSET_UPDATE_IOS[0]:
            names += " (no asset update (ios))"     # v5.66: never offered to iPhones
        elif t == 10449 and assets:         # asset update check (v5.31, #292)
            r, info = assets.reply_10449(member)
            if r is not None:
                answers[10449] = r
            names += f" ({info})"
        elif t == 10748 and (NEWS[0] is not None or NEWS_TEST[0] or friends):
            # news room (v5.85): --news broadcast + test file (v5.55) + invites (v5.56), merged
            r, info = news_room_reply(member if member and member != NO_MEMBER else None, build,
                                      is_iphone(h, build), friends,
                                      lambda m: times.display_name(times.by_member.get(m, "")))
            if r is not None:
                answers[10748] = r
            if info:
                names += f" ({info})"
        elif t == 10455 and friends:        # an OMP invite (v5.56, #427): kept, never answered
            invitee, f = parse_invite_request(p)
            if invitee is None:
                names += f" (invite not read: {f})"
            else:
                ok = friends.are_friends(key, times.by_member.get(invitee, "")) if member else False
                names += f" ({OMP_INVITES[0].add(member, invitee, f, time.time(), ok)})"
        elif t == 10781 and (PRIZE_TEST or PRIZES[0]):     # prize list (v5.39 test, v5.76 table; #193)
            r, info = prize_reply(member, key, times)
            if r is not None:
                answers[10781] = r
            names += f" ({info})"
        elif t == 10556 and friends:        # social friends' member ids (v5.16)
            r, info = social_friends_reply(key, times, friends)
            answers[10556] = r
            names += f" ({info})"
        elif t == 10472 and friends:        # friends' details (v5.53, #278)
            r, info = friend_details_reply(p, key, times, friends)
            answers[10472] = r
            names += f" ({info})"
    for t, _t2, _z, p in subs:              # each for its own event (v5.30)
        if t == 10477:
            rows, me = times.rows(blob.leaderboard_request(p), key)
            total = len(rows)
            rows, me = top_rows(rows, me)
            answers.setdefault(10477, []).append(blob.leaderboard_rows(rows, me, total))
        elif t == 10484:
            answers.setdefault(10484, []).append(group_answer(p, times, key))
    # v5.63 (#501): 48 (download) is phase (b), not answered; 47 (list) only
    # as the empty list above (v5.64, --cloud-save).
    # 10555 (validate) is never answered: an empty or missing answer means
    # "valid", 0 makes the game delete the player's progress
    # (analysis/cloud-save.md 2.4).
    for t in (10555, 48):
        answers.pop(t, None)
    if not saves:
        answers.pop(47, None)
    names = f"player {who} member {member}: request " + names
    if not answers:
        return None, names
    r = blob.reply(plain, answers, int(time.time()), member_id=member)
    return blob.wrap(blob.wrap(r, 1), 2, seed=int(time.time()) & 0xFF), names


class CappedHTTPServer(http.server.ThreadingHTTPServer):
    """ThreadingHTTPServer that handles at most max_connections
    connections at once (v5.10, issue #143 8.5); a connection past that is
    closed at once instead of getting a thread. v5.81 (#248): connections
    from this machine (Caddy: forward_auth, proxied site and asset
    requests) count against their own local_connections slots, so a flood
    of them never takes a phone's slot; local_connections 0 = one pool.
    v5.83 (#248): a listen backlog of listen_queue (was Python's 5), an
    idle connection waits at most keepalive_s for its next request (the
    handler reads it), at most per_ip phone connections per IP (0 = no
    cap), and counters for the once-a-minute "slots:" line."""
    daemon_threads = True

    def __init__(self, address, handler, max_connections=MAX_CONNECTIONS, local_connections=0,
                 listen_queue=LISTEN_QUEUE, keepalive_s=KEEPALIVE_S, per_ip=PER_IP):
        self.max_connections = max_connections
        self.local_connections = local_connections
        self.slots = threading.BoundedSemaphore(max_connections)
        self.local_slots = threading.BoundedSemaphore(local_connections) if local_connections else None
        self.refused = 0
        self.local_refused = 0
        self.ip_refused = 0
        self.request_queue_size = listen_queue      # read by server_activate() in super().__init__
        self.keepalive_s = keepalive_s
        self.per_ip = per_ip
        self.stats_lock = threading.Lock()
        self.busy = {False: 0, True: 0}             # local? -> connections being handled now
        self.peak = {False: 0, True: 0}             # the most at once this minute
        self.ip_open = {}                           # phone IP -> its connections being handled now
        self.ip_peak = 0                            # the most one IP held at once this minute
        self.minute = self.new_minute()
        super().__init__(address, handler)

    def new_minute(self):
        return {"refused": self.refused, "local_refused": self.local_refused, "ip_refused": self.ip_refused,
                "requests": 0, "ms": 0.0, "max_ms": 0.0, "max_what": "", "lock_max_ms": 0.0}

    def note_request(self, ms, lock_ms, what):
        """The handler's timing of one request (v5.83)."""
        with self.stats_lock:
            m = self.minute
            m["requests"] += 1
            m["ms"] += ms
            if ms > m["max_ms"]:
                m["max_ms"], m["max_what"] = ms, what
            m["lock_max_ms"] = max(m["lock_max_ms"], lock_ms)

    def stats_line(self):
        """The "slots:" line for the minute just ended; starts a new minute."""
        with self.stats_lock:
            m, self.minute = self.minute, self.new_minute()
            busy, peak = dict(self.busy), dict(self.peak)
            self.peak = dict(self.busy)
            ip_now = max(self.ip_open.values(), default=0)
            ip_peak, self.ip_peak = self.ip_peak, ip_now
        avg = m["ms"] / m["requests"] if m["requests"] else 0
        line = (f"slots: phone {busy[False]} busy (peak {peak[False]} of {self.max_connections})"
                + (f", local {busy[True]} (peak {peak[True]} of {self.local_connections})"
                   if self.local_slots is not None else "")
                + f"; refused this minute: {self.refused - m['refused']} phone"
                + (f", {self.local_refused - m['local_refused']} local" if self.local_slots is not None else "")
                + (f", {self.ip_refused - m['ip_refused']} per-IP" if self.per_ip else "")
                + f" (since start {self.refused}"
                + (f", {self.local_refused}" if self.local_slots is not None else "")
                + (f", {self.ip_refused}" if self.per_ip else "") + ")"
                + f"; {m['requests']} requests, avg {avg:.0f} ms, max {m['max_ms']:.0f} ms"
                + (f" ({m['max_what']})" if m["max_what"] else "")
                + f", lock wait max {m['lock_max_ms']:.0f} ms"
                + f"; most from one IP {ip_peak}" + (f" (cap {self.per_ip})" if self.per_ip else ""))
        return line

    def start_stats(self, every=STATS_S):
        def run():
            while True:
                time.sleep(every)
                print(f"[----] {datetime.datetime.now().strftime('%H:%M:%S.%f')[:12]} {self.stats_line()}",
                      flush=True)
        threading.Thread(target=run, daemon=True).start()

    def take_ip(self, ip):
        """Count a phone connection from ip; False if ip is at the per-IP cap."""
        with self.stats_lock:
            n = self.ip_open.get(ip, 0)
            if self.per_ip and n >= self.per_ip:
                return False
            self.ip_open[ip] = n + 1
            self.ip_peak = max(self.ip_peak, n + 1)
            return True

    def drop_ip(self, ip):
        with self.stats_lock:
            n = self.ip_open.get(ip, 0) - 1
            if n > 0:
                self.ip_open[ip] = n
            else:
                self.ip_open.pop(ip, None)

    def count_busy(self, local, d):
        with self.stats_lock:
            self.busy[local] += d
            self.peak[local] = max(self.peak[local], self.busy[local])

    def slots_for(self, client_address):
        """(semaphore, local?) for a connection from client_address."""
        if self.local_slots is not None and client_address and client_address[0] in ("127.0.0.1", "::1"):
            return self.local_slots, True
        return self.slots, False

    def process_request(self, request, client_address):
        slots, local = self.slots_for(client_address)
        ip = client_address[0] if client_address else ""
        if not local and not self.take_ip(ip):      # v5.83: per-IP cap (phones only)
            self.ip_refused += 1
            n = self.ip_refused
            if n in (1, 10, 100) or n % 1000 == 0:
                print(f"[----] connection from {ip} refused: {n} so far "
                      f"(per-IP cap {self.per_ip} reached)", flush=True)
            self.shutdown_request(request)
            return
        if not slots.acquire(blocking=False):
            if not local:
                self.drop_ip(ip)
            if local:
                self.local_refused += 1
                n, size, kind = self.local_refused, self.local_connections, "local slots"
            else:
                self.refused += 1
                n, size, kind = self.refused, self.max_connections, "slots"
            if n in (1, 10, 100) or n % 1000 == 0:
                print(f"[----] connection from {client_address[0]} refused: "
                      f"{n} so far (all {size} {kind} busy)", flush=True)
            self.shutdown_request(request)
            return
        self.count_busy(local, 1)
        try:
            super().process_request(request, client_address)
        except Exception:
            self.release(client_address)
            raise

    def release(self, client_address):
        slots, local = self.slots_for(client_address)
        self.count_busy(local, -1)
        if not local:
            self.drop_ip(client_address[0] if client_address else "")
        slots.release()

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], OSError):   # the client went away (or the deadline cut it)
            return
        super().handle_error(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.release(client_address)


class BadBody(Exception):
    """A request body the server will not read; args[0] = HTTP status."""


WEB_PREFIX = "/prr/"            # the friends site's path on the public host (issue #218)
ATTEST_PREFIX = "/prr/attest"   # key attestation endpoints (v5.38, issue #204)
ATT_CHECK_PATH = "/prr/api/att/check"   # v5.58 (#452): token check for other servers
ATT_CHECK_BODY_MAX = 2048       # {"token", "sig", "ip"}
ASSET_GATE_PATH = "/prr-gate/asset"     # v5.62 (#248): Caddy's forward_auth; under no public route
ASSET_GATE_PREFIXES = ("/rr3/live/", "/assetman/")      # what the gate may be asked about
ASSET_GATE_CACHE_S = 60         # verdict cache per token and IP: a pack is many Range requests
ASSET_GATE_CACHE_MAX = 10000
# v5.44 (#359): every /prr/ response refuses to be framed (clickjacking; the
# site is linked from prr3.devel60.net, never embedded).
NO_FRAME_HEADERS = (("Content-Security-Policy", "frame-ancestors 'none'"),
                    ("X-Frame-Options", "DENY"))
ATTEST_BODY_MAX = 64 * 1024     # a chain is a few KB
WEB_BODY_MAX = 4096             # largest API request body
CLOUDSAVE_DEFER = -1            # v5.72: web_answer's "answer me/cloudsave outside the server lock"
WEB_ACTIONS = ("request", "accept", "reject", "cancel", "remove")
COOKIE = "prr_session"


# Public results API (v5.47, #360; #359 R1-R11): read-only GETs under
# /prr/api/ that need no login, checked before the cookie test (R11).
PUBLIC_RE = re.compile(r"(matches|match/\d{1,10}|player/[0-9a-f]{12}/matches|players|live|top|status|ratings)")
# v5.68: live; v5.71: top (#542), status (#374)
PUBLIC_HEADERS = {"Cache-Control": "max-age=30", "X-Robots-Tag": "noindex"}   # R7, R8
PUBLIC_PER_MIN = 120            # public GETs one IP may make per minute (#143); more get 429
PUBLIC_IPS_MAX = 10000          # IPs remembered for that (oldest forgotten first)
PAGE_DEFAULT, PAGE_MAX = 20, 50
PLAYERS_MAX = 10                # players?q= answers at most (R2)
NAME_GUEST, NAME_HIDDEN = "Guest", "Player"
# v5.68 (#522): live status
LIVE_ONLINE_S = 300             # "online" = a game request in the last 5 min
LIVE_LOG_S = 60                 # the "live:" log line, once a minute
LIVE_KEYS_MAX = 20000           # players remembered (oldest forgotten first)
LIVE_HEADERS = {"Cache-Control": "max-age=15", "X-Robots-Tag": "noindex"}
# v5.71 (#542, #374)
LIVE_KEEP_S = 3600              # last-seen times kept this long (online_1h)
MP_STATUS_STALE_S = 60          # rr3_mp_server.py's --status-file older than this is ignored
MP_ROOMS_MAX = 200              # rooms read from it at most
TOP_N = 10                      # /prr/api/top entries per board
TOP_HEADERS = {"Cache-Control": "max-age=60", "X-Robots-Tag": "noindex"}
STATUS_HEADERS = {"Cache-Control": "max-age=30", "X-Robots-Tag": "noindex"}


class LiveSeen:
    """When each player last made a game request (v5.68, #522): {member id,
    or the phone's player key without one: unix time}, memory only (a
    restart starts at 0). Re-inserted on every request, so the dict is
    oldest first and online() drops from the front. The caller holds the
    server lock."""

    def __init__(self, window=LIVE_ONLINE_S, keys_max=LIVE_KEYS_MAX, keep=LIVE_KEEP_S):
        self.window, self.keys_max, self.keep = window, keys_max, max(keep, window)
        self.last = {}
        self.day, self.today = None, set()      # v5.71 (#374): players seen this UTC day
        self.since = time.time()                # the counts start here (memory only)

    def seen(self, member, key, now):
        """A request from this player (v5.68: a sync; v5.69: any request
        naming a member, see the handler). member = their member id (None
        or NO_MEMBER: none), key = their player key; a request without
        either ("unknown": no phone id) is not counted."""
        k = member if member and member != NO_MEMBER else (None if key in (None, "", "unknown") else key)
        if k is None:
            return
        self.last.pop(k, None)
        self.last[k] = now
        while len(self.last) > self.keys_max:
            del self.last[next(iter(self.last))]
        day = utc_date(now)
        if day != self.day:
            self.day, self.today = day, set()
        if len(self.today) < self.keys_max:
            self.today.add(k)

    def online(self, now, window=None):
        """Players seen in the last window seconds (default self.window;
        v5.71: entries older than keep are dropped, the newest are counted
        from the end)."""
        while self.last:
            k = next(iter(self.last))
            if now - self.last[k] < self.keep:
                break
            del self.last[k]
        window = self.window if window is None else window
        n = 0
        for t in reversed(self.last.values()):
            if now - t >= window:
                break
            n += 1
        return n

    def players_today(self, now):
        """Players seen since 00:00 UTC (v5.71, #374)."""
        return len(self.today) if self.day == utc_date(now) else 0


LIVE_SEEN = [LiveSeen()]


def live_log(store, live, now):
    """"online N, racing M, rooms K, lobby L" for the once-a-minute log
    line (#522; v5.71: lobby rooms, #542)."""
    return live_answer(store, {}, live, now, mp=MP_STATUS[0])[1]


class MpStatus:
    """rr3_mp_server.py v0.28's --status-file (v5.71, #542, #374), read
    via --mp-status: re-read when it changes (checked at most once a
    second). get(now) = the file's dict, or None when it is missing,
    unreadable or its "updated" is older than MP_STATUS_STALE_S. The
    member ids in it never leave CC."""

    def __init__(self, path, clock=time.monotonic):
        self.path, self.clock = path, clock
        self.data, self.stamp, self.next_check = None, None, 0.0

    def get(self, now):
        if not self.path:
            return None
        if self.clock() >= self.next_check:
            self.next_check = self.clock() + 1.0
            try:
                st = os.stat(self.path)
                if (st.st_mtime_ns, st.st_size) != self.stamp:
                    with open(self.path, encoding="utf-8") as f:
                        d = json.load(f)
                    self.data, self.stamp = (d if isinstance(d, dict) else None), (st.st_mtime_ns, st.st_size)
            except (OSError, ValueError):
                self.data, self.stamp = None, None
        d = self.data
        try:
            if d is None or now - float(d.get("updated")) > MP_STATUS_STALE_S:
                return None
        except (TypeError, ValueError):
            return None
        return d


MP_STATUS = [MpStatus(None)]            # replaced by main() (--mp-status)


def mp_rooms(d):
    """The room entries of MP's status dict, checked: (state, private,
    league, players, max, seconds, [member ids]); bad entries skipped."""
    out = []
    for r in (d.get("room_list") if d else None) or []:
        try:
            members = [int(m) for m in r.get("members") or []][:ROOM_MAX_MP]
            out.append((str(r["state"]), bool(r.get("private")), int(r.get("league") or 0),
                        int(r["players"]), int(r["max"]) if r.get("max") is not None else None,
                        max(0, int(r.get("seconds") or 0)), [m for m in members if 0 < m < 0x80000000]))
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        if len(out) >= MP_ROOMS_MAX:
            break
    return out


ROOM_MAX_MP = 43                        # the game's lobby slots (rr3_mp_server.py ROOM_MAX)


def card_names(members, players, times, store, hidden):
    """Names for a public room card (v5.71, #542 D3): the current name of
    each member, "Player N" (N = place in the card) for a hidden or
    shadowed player or an unknown member, "Guest" without a member, padded
    with "Guest" up to players."""
    names = []
    for m in members:
        n = public_person(m, times, store, hidden)["name"] if m else NAME_GUEST
        names.append(f"{NAME_HIDDEN} {len(names) + 1}" if n == NAME_HIDDEN else n)
    return (names + [NAME_GUEST] * max(0, players - len(names)))[:max(players, 0)]


def live_answer(store, track_names, live, now, times=None, hidden=(), mp=None):
    """GET /prr/api/live (v5.68, #522): players online and the rooms
    racing now, i.e. the open matches with a StartMatch (some car not
    null), oldest first. An invite (private) or Race Selector room shows
    only private, players and minutes; minutes = whole minutes since the
    room's start. v5.71 (#542): every room has "state" ("racing" or
    "lobby") and "max"; public rooms have "names" (with times; card_names);
    "lobby" = MP's rooms not started yet (mp: MpStatus), oldest first,
    except one whose members are already racing here; "rooms_open",
    "in_lobby". No member ids, pids or timestamps."""
    d = mp.get(now) if mp is not None else None
    mp_list = mp_rooms(d)
    rooms, racing_members = [], set()
    for m in sorted(store.open.values(), key=lambda m: (m["started"], m["id"])):
        if not any(c is not None for _v, c in m["starters"]):
            continue
        members = [omp_member(v) for v, _c in m["starters"]]
        racing_members |= set(members) - {0}
        players, minutes = len(m["starters"]), max(0, int(now - m["started"]) // 60)
        size = next((r[4] for r in mp_list if set(r[6]) & set(members)), None)
        if m.get("private") or m.get("selector"):
            rooms.append({"private": True, "players": players, "minutes": minutes, "state": "racing",
                          "max": size})
        else:
            room = {"league": m.get("league"), "track": m["track"],
                    "track_name": track_names.get(m["track"]), "laps": m["laps"],
                    "players": players, "minutes": minutes, "private": False, "state": "racing", "max": size}
            if times is not None:
                room["names"] = card_names(members, players, times, store, hidden)
            rooms.append(room)
    lobby = []
    for state, private, league, players, size, seconds, members in sorted(mp_list, key=lambda r: -r[5]):
        if state == "started" or players <= 0 or set(members) & racing_members:
            continue
        room = {"state": "lobby", "private": private, "players": players, "max": size,
                "minutes": seconds // 60}
        if not private:
            room["league"] = league
            if times is not None:
                room["names"] = card_names(members, players, times, store, hidden)
        lobby.append(room)
    data = {"online": live.online(now), "racing": sum(r["players"] for r in rooms),
            "rooms": rooms, "window_s": live.window, "lobby": lobby,
            "in_lobby": sum(r["players"] for r in lobby), "rooms_open": len(rooms) + len(lobby)}
    return data, (f"online {data['online']}, racing {data['racing']}, rooms {len(rooms)}, "
                  f"lobby {len(lobby)}")


def utc_minute(t):
    """"YYYY-MM-DDTHH:MMZ" (v5.71: public answers carry nothing finer)."""
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def status_answer(store, live, now, mp=None, times=None):
    """GET /prr/api/status (v5.71, #374): counts only. MP's fields are
    None when its file is missing or stale. v5.77: "registered" = member ids
    given out (None without a Times). v5.85 (#644): "news" = [{"id",
    "sent"}] per --news message (members sent it since the start), only
    with --news."""
    d = mp.get(now) if mp is not None else None

    def mp_count(k):
        try:
            return int(d[k]) if d is not None else None
        except (KeyError, TypeError, ValueError):
            return None
    data = {"online_5m": live.online(now), "online_1h": live.online(now, 3600),
            "players_today": live.players_today(now), "races_today": store.settled_on(utc_date(now)),
            "rooms": mp_count("rooms"), "in_rooms": mp_count("in_rooms"), "searching": mp_count("searching"),
            "registered": len(times.by_member) if times is not None else None,
            "since": utc_minute(live.since), "updated": utc_minute(now)}
    if NEWS[0] is not None:             # v5.85 (#644): only with --news
        data["news"] = NEWS[0].status()
    return data, (f"online {data['online_5m']}, today {data['players_today']}, races {data['races_today']}, "
                  f"registered {data['registered']}")


def top_answer(store, times, hidden):
    """GET /prr/api/top (v5.71, #542 D5): {"wins", "podiums", "races":
    [{pos, name, value}] x 10, "races_counted", "updated"}. The boards come
    from OmpStore.top() (counted at index time); only names are looked up
    here. Hidden or shadowed players = "Player N" (N = their place);
    banned players (v5.80, #607) are left out."""
    boards = store.top(times.member_banned if times is not None else None)
    data = {}
    for kind in ("wins", "podiums", "races"):
        rows = []
        for i, (member, value) in enumerate(boards[kind], 1):
            n = public_person(member, times, store, hidden)["name"]
            rows.append({"pos": i, "name": f"{NAME_HIDDEN} {i}" if n == NAME_HIDDEN else n, "value": value})
        data[kind] = rows
    data["races_counted"] = store.top_races
    data["updated"] = utc_minute(store.top_updated) if store.top_updated else None
    return data, f"{store.top_races} races counted"


class HiddenList:
    """Members hidden from public pages on request (v5.47, #359 R6):
    --public-hidden, default data/public-hidden.txt, one `member N` per
    line, `#` comments. Also the leaderboard ban list (v5.80, #607,
    --lb-banned; label and diff: its log text, with who changed). Re-read when it changes (checked at most once a
    second; no restart); a missing file hides nobody, a bad line is
    logged and skipped, an unreadable file keeps the last list."""

    def __init__(self, path, log=print, clock=time.monotonic, label="public-hidden list", diff=False,
                 actions=False):
        self.path, self.log, self.clock, self.label, self.diff = path, log, clock, label, diff
        # v5.84 (#606): with actions (--lb-banned), also `approve|reject member N
        # event E time T` lines, kept as (verb, N, E, T); Times.apply_actions acts on them.
        self.allow_actions, self.actions = actions, frozenset()
        self.members, self.stamp, self.next_check = frozenset(), None, 0.0
        self.refresh(force=True)

    def refresh(self, force=False):
        if not self.path or (not force and self.clock() < self.next_check):
            return
        self.next_check = self.clock() + 1.0
        try:
            st = os.stat(self.path)
        except OSError:
            if self.stamp is not None:
                self.log(f"{self.label} {self.path} removed: nobody " + ("banned" if self.diff else "hidden")
                         + (f" (-{', -'.join(map(str, sorted(self.members)))})" if self.diff and self.members else ""))
            self.members, self.actions, self.stamp = frozenset(), frozenset(), None
            return
        if (st.st_mtime_ns, st.st_size) == self.stamp:
            return
        try:
            with open(self.path, encoding="utf-8-sig") as f:
                lines = f.read().splitlines()
        except (OSError, UnicodeError) as e:
            self.log(f"{self.label} {self.path}: {e}; keeping the last list")
            return
        members, actions = set(), set()
        for n, line in enumerate(lines, 1):
            rule = line.split("#", 1)[0].split()
            if not rule:
                continue
            if len(rule) == 2 and rule[0].lower() == "member" and rule[1].isdigit():
                members.add(int(rule[1]))
            elif (self.allow_actions and len(rule) == 7 and rule[0].lower() in ("approve", "reject")
                  and [w.lower() for w in rule[1::2]] == ["member", "event", "time"]
                  and all(w.isdigit() for w in rule[2::2])):
                actions.add((rule[0].lower(), int(rule[2]), int(rule[4]), int(rule[6])))
            else:
                self.log(f"{self.label} {self.path}: line {n} not understood, skipped")
        if self.stamp is not None or members:
            change = ""
            if self.diff:               # v5.80 (#607): who was added and removed
                change = ", ".join([f"+{m}" for m in sorted(members - self.members)]
                                   + [f"-{m}" for m in sorted(self.members - members)])
            self.log(f"{self.label} {self.path}: {len(members)} member(s)" + (f" ({change})" if change else ""))
        if actions != self.actions:
            self.log(f"{self.label} {self.path}: {len(actions)} approve/reject line(s)")
        self.members, self.actions, self.stamp = frozenset(members), frozenset(actions), (st.st_mtime_ns, st.st_size)

    def __contains__(self, member):
        self.refresh()
        return member in self.members


class RateLimit:
    """At most n hits per IP in any window of seconds (v5.47)."""

    def __init__(self, n=PUBLIC_PER_MIN, window=60.0, ips_max=PUBLIC_IPS_MAX):
        self.n, self.window, self.ips_max = n, window, ips_max
        self.hits = {}

    def allow(self, ip, now):
        recent = [t for t in self.hits.pop(ip, []) if now - t < self.window]
        ok = len(recent) < self.n
        self.hits[ip] = recent + [now] if ok else recent      # re-inserted: least recent first
        while len(self.hits) > self.ips_max:
            del self.hits[next(iter(self.hits))]
        return ok


def page_args(query):
    """(before id or None, limit) from ?before=&limit= (default 20, max 50)."""
    try:
        before = int(query.get("before", [""])[0])
    except ValueError:
        before = None
    try:
        limit = int(query.get("limit", [""])[0])
    except ValueError:
        limit = PAGE_DEFAULT
    return before, min(max(limit, 1), PAGE_MAX)


RATINGS_PAGE_DEFAULT, RATINGS_PAGE_MAX = 50, 100


def ratings_answer(ratings, query, times, store, hidden, now):
    """GET /prr/api/ratings?limit=&offset= (v5.79, #263 item 10). While
    ratings are not on: {"ranked": false, "starts": "YYYY-MM-DD" or null},
    never a shadow number. On: {"ranked": true, "starts", "players": [{pos,
    name, pid, rating, races, finished}], "total", "next" (offset or
    null)}. Hidden or shadowed players = "Player", no pid, keep their
    place; banned ones (v5.80, #607) are left out. No member ids."""
    if ratings.mode_at(now) != "on":
        return {"ranked": False, "starts": ratings.start}, "not on (" + ratings.mode_at(now) + ")"

    def num(k, default):
        try:
            return int(query.get(k, [""])[0])
        except ValueError:
            return default
    limit = min(max(num("limit", RATINGS_PAGE_DEFAULT), 1), RATINGS_PAGE_MAX)
    offset = max(num("offset", 0), 0)
    board = ratings.leaderboard()
    if times is not None:               # v5.80 (#607): banned players left out
        board = [x for x in board if not times.member_banned(x[0])]
    rows = [dict(pos=i, **public_person(m, times, store, hidden), rating=e["rating"], races=e["races"],
                 finished=e["finished"])
            for i, (m, e) in enumerate(board[offset:offset + limit], offset + 1)]
    nxt = offset + limit if offset + limit < len(board) else None
    return ({"ranked": True, "starts": ratings.start, "players": rows, "total": len(board), "next": nxt},
            f"{len(rows)} of {len(board)}")


def public_person(member, times, store, hidden):
    """{"name", "pid"} for a public answer (#359 Names): the current name;
    a guest = "Guest", a shadowed, hidden or banned (v5.80) player =
    "Player"; both with pid None (no player page, no link). Never the member id (decision 6)."""
    if not member:
        return {"name": NAME_GUEST, "pid": None}
    key = times.by_member.get(member)
    if key is None:
        return {"name": NAME_HIDDEN, "pid": None}
    if member in hidden or times.hidden(key, None):
        return {"name": NAME_HIDDEN, "pid": None}
    return {"name": times.display_name(key), "pid": store.pid(member)}


def race_head(rec, track_names):
    """Public head of a record: date only (R4), never started / settled."""
    return {"id": rec["id"], "date": utc_date(rec["started"]), "track": rec["track"],
            "track_name": track_names.get(rec["track"]), "laps": rec["laps"],
            "league": rec.get("league"), "ranked": bool(rec.get("ranked")),
            "private": bool(rec.get("private")), "selector": bool(rec.get("selector"))}


def own_row(rec, member):
    return next((p for p in rec["players"] if p["member"] == member), None)


def omp_forfeit(rec):
    """v5.84 (#606 O4): the player row that "won by forfeit" in a settled
    record: the only finisher of a room of 2+
    starters whose others all left or did not finish (the race ends at
    once for the last player, so the time means nothing). None otherwise."""
    ps = rec.get("players", [])
    fin = [p for p in ps if p.get("status") == "finished"]
    if len(ps) >= 2 and len(fin) == 1 and all(p.get("status") in ("left", "dnf") for p in ps if p is not fin[0]):
        return fin[0]
    return None


def time_fields(rec, p):
    """{"time_ms": .., ["forfeit": True]} for player row p of rec (#606 O4: no time for a forfeit win)."""
    if p is not None and p is omp_forfeit(rec):
        return {"time_ms": None, "forfeit": True}
    return {"time_ms": (p or {}).get("time_ms")}


def public_answer(what, query, times, store, hidden, track_names, car_names):
    """One public results GET (#360; #359 Endpoints). Returns (status,
    body, log text). No member ids and no timestamps in any answer."""
    before, limit = page_args(query)
    if what == "matches":
        recs, nxt = store.page(None, before, limit)
        out = []
        for rec in recs:
            win = rec["players"][0] if rec["players"] else None
            row = dict(race_head(rec, track_names), starters=len(rec["players"]), winner=None)
            if win and win["status"] == "finished":
                row["winner"] = dict(public_person(win["member"], times, store, hidden), **time_fields(rec, win))
            out.append(row)
        return 200, {"matches": out, "next": nxt}, f"{len(out)} races"
    if what.startswith("match/"):
        i = store.by_id.get(int(what[6:]))
        if i is None:
            return 404, {"error": "no such race"}, "no such race"
        rec = store.records[i]
        players = []
        for p in rec["players"]:
            row = dict(position=p["position"], **public_person(p["member"], times, store, hidden),
                       car=p["car"], car_name=car_names.get(p["car"]), status=p["status"], **time_fields(rec, p))
            if rec.get("ranked"):
                row.update(rating_before=p.get("rating_before"), rating_after=p.get("rating_after"))
            players.append(row)
        return 200, dict(race_head(rec, track_names), players=players), f"race {rec['id']}"
    if what.startswith("player/"):
        member = store.pids.get(what.split("/")[1])
        if member is None or member in hidden:
            return 404, {"error": "no such player"}, "no such player"
        person = public_person(member, times, store, hidden)
        if person["pid"] is None:                       # shadowed (or no key)
            return 404, {"error": "no such player"}, "no such player"
        recs, nxt = store.page(store.by_member.get(member, []), before, limit)
        out = []
        for rec in recs:
            me = own_row(rec, member) or {}
            row = dict(race_head(rec, track_names), starters=len(rec["players"]), position=me.get("position"),
                       status=me.get("status"), **time_fields(rec, own_row(rec, member)), car=me.get("car"),
                       car_name=car_names.get(me.get("car")))
            if rec.get("ranked") and me.get("rating_after") is not None and me.get("rating_before") is not None:
                row["rating_change"] = me["rating_after"] - me["rating_before"]
            out.append(row)
        return 200, dict(person, matches=out, next=nxt), f"player: {len(out)} races"
    # players?q=
    q = query.get("q", [""])[0].strip().lower()[:24]
    out = []
    if len(q) >= 2:
        for member in sorted(store.by_member):
            if member in hidden:
                continue
            person = public_person(member, times, store, hidden)
            if person["pid"] and q in person["name"].lower():
                out.append(person)
                if len(out) >= PLAYERS_MAX:
                    break
    return 200, {"players": out}, f"players: {len(out)} found"


def my_matches(member, me, query, times, store, track_names, car_names):
    """me/matches (cookie, #360): your races with full timestamps, your
    member id and pid (R3). Works for a hidden or shadowed player."""
    before, limit = page_args(query)
    recs, nxt = store.page(store.by_member.get(member, []), before, limit)
    out = []
    for rec in recs:
        p = own_row(rec, member) or {}
        row = dict(race_head(rec, track_names), started=rec["started"], settled=rec["settled"],
                   starters=len(rec["players"]), position=p.get("position"), status=p.get("status"),
                   **time_fields(rec, own_row(rec, member)), car=p.get("car"), car_name=car_names.get(p.get("car")))
        if rec.get("ranked") and p.get("rating_after") is not None and p.get("rating_before") is not None:
            row["rating_change"] = p["rating_after"] - p["rating_before"]
        out.append(row)
    return {"member": member, "pid": store.pid(member), "name": times.display_name(me),
            "races_finished": store.races_finished(member), "matches": out, "next": nxt}


def is_admin(times, member):
    """v5.84 (#606): may member use the admin page (--lb-admins)?"""
    return bool(member) and member != NO_MEMBER and member in getattr(times, "admins", ())


def admin_held_action(times, admin, action, member, event, time_ms, now):
    """POST /prr/api/admin/held (v5.84, #606): approve or reject a held
    time, or ban its member. The line goes into --lb-banned (so the file
    records who did what) and approve/reject act at once. Returns (status,
    headers, body)."""
    path = getattr(times.lb_banned, "path", None)
    if not path:
        return 409, {}, {"error": "no --lb-banned file"}
    if action != "ban" and time_ms not in [h["time_ms"] for h in times.held_list()
                                           if h["member"] == member and h["event"] == event]:
        return 404, {}, {"error": "no such held time"}
    stamp = datetime.datetime.fromtimestamp(now, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    line = (f"member {member}   # banned on the admin page (event {event}, {time_ms} ms)"
            if action == "ban" else f"{action} member {member} event {event} time {time_ms}   #")
    line += f" by member {admin}, {stamp} UTC"
    try:
        lead = ""
        if os.path.exists(path) and os.path.getsize(path):
            with open(path, "rb") as f:
                f.seek(-1, os.SEEK_END)
                lead = "" if f.read(1) == b"\n" else "\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(lead + line + "\n")
    except OSError as e:
        return 500, {}, {"error": f"can't write {os.path.basename(path)}: {e}"}
    if action == "ban":
        times.lb_banned.refresh(force=True)
        return 200, {}, {"ok": True}
    why = times.admin_act(action, member, event, time_ms, f"member {admin}")
    return (409, {}, {"error": why}) if why else (200, {}, {"ok": True})


def web_answer(method, path, query, headers, body, ip, times, friends, now=None, blocklist=None,
               store=None, hidden=(), limiter=None, track_names=None, car_names=None):
    """The friends site's login and API (v5.16, issue #218). Returns
    (status, extra headers, JSON-able body or None, line for the log).
    GET /prr/login?v=1&m=<member>&c=<code>: checks the code, sets the
    session cookie and redirects to /prr/ (the code leaves the address).
    /prr/api/...: me, friends, search?q= (GET); request, accept, reject,
    cancel, remove {"member": n}, logout, logout-all (POST, header X-PRR: 1).
    Every answer but the login needs the session cookie. A member on
    blocklist (v5.37, #332) can't log in, and their session gets 403.
    v5.47 (#360): with store (OmpStore), the public results GETs
    (PUBLIC_RE: matches, match/<id>, player/<pid>/matches, players?q=)
    are answered before the cookie test, with PUBLIC_HEADERS and at most
    limiter's rate per IP (429 past it); me/matches needs the cookie.
    v5.68 (#522): live, the same way, with LIVE_HEADERS (max-age=15).
    hidden = members hidden from public answers (HiddenList, R6);
    track_names / car_names = {id: name} for the site."""
    now = time.time() if now is None else now
    jar = http.cookies.SimpleCookie()
    try:
        jar.load(headers.get("Cookie") or "")
    except http.cookies.CookieError:
        pass
    token = jar[COOKIE].value if COOKIE in jar else ""
    if path == WEB_PREFIX + "login":
        if method != "GET":
            return 405, {}, None, "login: not GET"
        try:
            member = int(query.get("m", [""])[0])
        except ValueError:
            member = 0
        code = query.get("c", [""])[0]
        if blocklist and blocklist.member(member):
            return 302, {"Location": WEB_PREFIX + "?login=failed"}, None, f"login member {member}: blocked"
        key = times.by_member.get(member)
        ok, why = friends.check_login(key, member, code, ip, now) if key else (False, "unknown member")
        if not ok and why == "used code" and friends.session(token, now) == key:
            # v5.17: the same tap again while still logged in as that player
            return 302, {"Location": WEB_PREFIX}, None, f"login member {member}: used code, already logged in"
        if not ok:
            # v5.54 (#423): say why when the phone's secret changed (the dashboard can show it)
            reason = "&reason=secret-changed" if why.startswith("wrong code (phone's") else ""
            return 302, {"Location": WEB_PREFIX + "?login=failed" + reason}, None, f"login member {member}: {why}"
        t = friends.new_session(key, now)
        return 302, {"Location": WEB_PREFIX,
                     "Set-Cookie": f"{COOKIE}={t}; Path={WEB_PREFIX}; Secure; HttpOnly; SameSite=Lax"
                     }, None, f"login member {member}: ok"
    if not path.startswith(WEB_PREFIX + "api/"):
        return 404, {}, None, "not found"
    what = path[len(WEB_PREFIX + "api/"):]
    track_names, car_names = track_names or {}, car_names or {}
    if store is not None and PUBLIC_RE.fullmatch(what):
        if method != "GET":
            return 405, {}, {"error": "method"}, f"public {what}: not GET"
        if limiter is not None and not limiter.allow(ip, now):
            return 429, {}, {"error": "too many requests"}, f"public {what}: rate limited"
        if what == "live":                      # v5.68 (#522); v5.71: lobby rooms and names (#542)
            data, info = live_answer(store, track_names, LIVE_SEEN[0], now, times, hidden, MP_STATUS[0])
            return 200, dict(LIVE_HEADERS), data, f"public live: {info}"
        if what == "top":                       # v5.71 (#542)
            data, info = top_answer(store, times, hidden)
            return 200, dict(TOP_HEADERS), data, f"public top: {info}"
        if what == "ratings":                   # v5.79 (#263)
            data, info = ratings_answer(store.ratings, query, times, store, hidden, now)
            return 200, dict(TOP_HEADERS), data, f"public ratings: {info}"
        if what == "status":                    # v5.71 (#374)
            data, info = status_answer(store, LIVE_SEEN[0], now, MP_STATUS[0], times)
            return 200, dict(STATUS_HEADERS), data, f"public status: {info}"
        code, data, info = public_answer(what, query, times, store, hidden, track_names, car_names)
        return code, dict(PUBLIC_HEADERS), data, f"public {what}: {info}"
    me = friends.session(token, now)
    if me is None:
        return 401, {}, {"error": "not logged in"}, f"api {what}: not logged in"
    my_member = times.members.get(me, 0)
    who = f"api {what} member {my_member}"
    if blocklist and blocklist.member(my_member):
        return 403, {}, {"error": "blocked"}, f"{who}: blocked"
    if method == "GET":
        if what == "me":
            data = {"member": my_member, "name": times.display_name(me)}
            if is_admin(times, my_member):      # v5.84 (#606): the site shows the Admin tab
                data["admin"] = True
            if times.name_taken(me):            # v5.74 (#178)
                data["name_taken"] = times.name_taken(me)
            return 200, {}, data, who
        if what == "me/matches" and store is not None:
            data = my_matches(my_member, me, query, times, store, track_names, car_names)
            return 200, {}, data, f"{who}: {len(data['matches'])} races"
        if what == "me/league":                 # v5.48 (#264)
            data = OMP_LEAGUES[0].info(my_member, (store or OMP_STORE[0]).races_finished(my_member))
            return 200, {}, data, f"{who}: league {data['league']}"
        if what == "me/cloudsave":              # v5.72 (#530): answered outside the lock (cloudsave_answer)
            return CLOUDSAVE_DEFER, {}, {"member": my_member, "what": what}, who

        def card(k, t):
            return {"member": times.members.get(k, 0), "name": times.display_name(k), "time": t}
        if what == "me/invites":                # v5.56 (#427): pending OMP invites to me
            now_s = time.time()
            out = []
            for r in OMP_INVITES[0].pending(my_member, now_s):
                owner_key = times.by_member.get(r["owner"], "")
                name = times.display_name(owner_key)
                link = invite_link(r)
                out.append({"room": r["room"], "from": {"member": r["owner"], "name": name},
                            "event": r["event"], "created": r["created"], "expires": r["expires"],
                            "link": link, "intent": invite_intent(link, f"{name} invited you to race")})
            return 200, {}, {"invites": out}, f"{who}: {len(out)} invite(s)"
        if what == "friends":
            return 200, {}, {
                "friends": sorted((card(k, friends.pairs[frozenset((me, k))]) for k in friends.friends_of(me)),
                                  key=lambda c: c["name"].lower()),
                "incoming": [card(a, t) for (a, b), t in friends.requests.items() if b == me],
                "outgoing": [card(b, t) for (a, b), t in friends.requests.items() if a == me]}, who
        if what == "search":
            q = query.get("q", [""])[0].strip().lower()[:24]
            if len(q) < 2:
                return 200, {}, {"results": []}, who
            mine = set(friends.friends_of(me))
            out = []
            for k, m in sorted(times.members.items(), key=lambda kv: kv[1]):
                if k == me or k in mine or times.hide_kind(k, me) == "shadow":   # banned: still findable (v5.80)
                    continue
                name = times.display_name(k)
                if q in name.lower():
                    out.append({"member": m, "name": name})
                    if len(out) >= SEARCH_MAX:
                        break
            return 200, {}, {"results": out}, f"{who}: {len(out)} found"
        if what == "admin/held":                # v5.84 (#606)
            if not is_admin(times, my_member):
                return 403, {}, {"error": "not an admin"}, f"{who}: not an admin"
            times.apply_actions()
            held = times.held_list()
            for h in held:
                h["reasons"] = [HOLD_REASONS.get(c, c) for c in h["held"]]
                h["car_name"] = (car_names or {}).get(h["car"])
            return 200, {}, {"held": held}, f"{who}: {len(held)} held"
        return 404, {}, {"error": "unknown"}, who
    if method != "POST":
        return 405, {}, {"error": "method"}, who
    if headers.get("X-PRR") != "1":
        return 403, {}, {"error": "missing X-PRR header"}, f"{who}: no X-PRR header"
    if what in ("logout", "logout-all"):
        friends.end_sessions(me, token if what == "logout" else None)
        return 200, {"Set-Cookie": f"{COOKIE}=; Path={WEB_PREFIX}; Max-Age=0; Secure; HttpOnly; SameSite=Lax"
                     }, {"ok": True}, who
    if what in ("me/cloudsave/preset", "me/cloudsave/own", "me/cloudsave/optout"):     # v5.72 (#530)
        if len(body) > WEB_BODY_MAX:
            return 413, {}, {"error": "too large"}, who
        return CLOUDSAVE_DEFER, {}, {"member": my_member, "what": what}, who
    if what == "me/league":                     # v5.48 (#264): {"league": 0 (automatic), 1, 2 or 3}
        if len(body) > WEB_BODY_MAX:
            return 413, {}, {"error": "too large"}, who
        try:
            league = json.loads(body or b"{}").get("league")
            if not isinstance(league, int) or isinstance(league, bool):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            return 400, {}, {"error": "league?"}, f"{who}: bad body"
        races = (store or OMP_STORE[0]).races_finished(my_member)
        why = OMP_LEAGUES[0].set_pick(my_member, league, races, now)
        if why:
            return 409, {}, {"error": why}, f"{who}: pick {league} refused ({why})"
        return 200, {}, OMP_LEAGUES[0].info(my_member, races), f"{who}: pick {league}"
    if what == "admin/held":                    # v5.84 (#606): {"action", "member", "event", "time_ms"}
        if not is_admin(times, my_member):
            return 403, {}, {"error": "not an admin"}, f"{who}: not an admin"
        if len(body) > WEB_BODY_MAX:
            return 413, {}, {"error": "too large"}, who
        try:
            q = json.loads(body or b"{}")
            action = q.get("action")
            m, ev, t = (int(q.get(f)) for f in ("member", "event", "time_ms"))
            if action not in ("approve", "reject", "ban"):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            return 400, {}, {"error": "action?"}, f"{who}: bad body"
        return admin_held_action(times, my_member, action, m, ev, t, now) + (f"{who} {action} {m} {ev} {t}",)
    if what not in WEB_ACTIONS:
        return 404, {}, {"error": "unknown"}, who
    if len(body) > WEB_BODY_MAX:
        return 413, {}, {"error": "too large"}, who
    try:
        other_member = int(json.loads(body or b"{}").get("member"))
    except (ValueError, TypeError, AttributeError):
        return 400, {}, {"error": "member?"}, f"{who}: bad body"
    other = times.by_member.get(other_member)
    if other is None or (what == "request" and times.hide_kind(other, me) == "shadow"):
        return 404, {}, {"error": "no such player"}, f"{who} {other_member}: no such player"
    why = friends.act(what, me, other, now)
    if why:
        return 409, {}, {"error": why}, f"{who} {other_member}: {why}"
    return 200, {}, {"ok": True}, f"{who} {other_member}: done"


def cloudsave_answer(saves, member, what, body, now=None):
    """The site's Cloud save page (v5.72, #530), outside the server lock
    (building a preset bundle unpacks and packs a few MB). web_answer has
    checked the login, the blocklist and, for POST, X-PRR and the size.
    -> (status, JSON body, log text)."""
    now = time.time() if now is None else now
    if saves is None:
        return 404, {"error": "cloud save is off"}, "cloud save off"
    if what == "me/cloudsave":
        info = saves.site_info(member, now)
        return 200, info, f"{len(info['versions'])} version(s), {info['picks_left']} pick(s) left"
    if what == "me/cloudsave/preset":
        try:
            pid = json.loads(body or b"{}").get("id")
            if not isinstance(pid, str):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            return 400, {"error": "id?"}, "preset: bad body"
        code, err, info = saves.site_preset(member, pid, now)
    elif what == "me/cloudsave/own":
        code, err, info = saves.site_own(member)
    else:
        code, err, info = saves.site_optout(member)
    if err:
        return code, {"error": err}, info
    return code, saves.site_info(member, now), info


def user_agent_tag(ua):
    """The PRR build tag in a User-Agent (v5.28, #272): the lib sends
    `RealRacing3/14.0.1 [PRR bNN-channel] Dalvik/...` on every request.
    None unless exactly one tag is there."""
    labels = BUILD_TAG_TEXT_RE.findall(ua or "")
    return labels[0] if len(labels) == 1 else None


def web_client_ip(peer, headers):
    """The client's address: behind Caddy (a request from this machine)
    the one Cloudflare or Caddy passed on, else the connection's own."""
    if peer in ("127.0.0.1", "::1"):
        fwd = headers.get("CF-Connecting-IP") or (headers.get("X-Forwarded-For") or "").split(",")[0]
        return fwd.strip() or peer
    return peer


def make_handler(outdir, status, times=None, ghosts=None, schedule=None, trusted=None, friends=None,
                 build_policy=None, assets=None, blocklist=None, attestation=None, results=None,
                 hidden=None, car_names=None, attest_enforce=False, token_key=None, admin_key=None,
                 attest_ios_exempt=False, asset_gate_enforce=False, saves=None):
    """results = the OmpStore for the public results API (v5.47, #360),
    hidden = its HiddenList, car_names = {car id: name}. attest_enforce
    (v5.57, #452): refuse syncs of players without a passing proof (needs
    attestation). token_key (v5.58, #452): 32 bytes; a passing proof gets a
    token for other servers, checked at ATT_CHECK_PATH with admin_key.
    attest_ios_exempt (v5.59, #451): with attest_enforce, answer an iPhone
    on an allowed iOS build with a player secret (ios_exempt()).
    asset_gate_enforce (v5.62, #248): refuse asset requests that fail the
    gate at ASSET_GATE_PATH (else log only; needs attestation and token_key).
    saves = CloudSaves (v5.63, #501, --cloud-save): answers 10660/10661/22
    and takes PUT /save/<key> up to saves.max_bytes; None = off."""
    if attest_enforce and attestation is None:
        raise ValueError("attest_enforce needs attestation")
    if asset_gate_enforce and (attestation is None or token_key is None or times is None):
        raise ValueError("asset_gate_enforce needs attestation and a token key")
    gate_cache = {}         # v5.62: (token, ip) -> (expires, reason, member, build)
    limiter = RateLimit()
    pending = {}            # v5.57: player key -> rrsecret of a refused sync (memory only)
    last_build = {}         # v5.58: player key -> build label of its latest sync past the build gate

    def remember_build(key, build):
        """Keep the build a player last synced with, for its token (#452)."""
        if key == "unknown":
            return
        last_build.pop(key, None)
        last_build[key] = build or ""
        while len(last_build) > PENDING_SECRETS_MAX:
            del last_build[next(iter(last_build))]

    def keep_pending(key, secret):
        """Remember a refused sync's secret for a player with no kept one,
        so /prr/attest can check the proof that sync starts (#452)."""
        if key == "unknown" or not secret or (friends and key in friends.secrets):
            return
        pending.pop(key, None)
        pending[key] = secret               # re-inserted: dict order = oldest first
        while len(pending) > PENDING_SECRETS_MAX:
            del pending[next(iter(pending))]

    def token_verdict(token, ip):
        """Is this attestation token good now (v5.58 check, shared since
        v5.62)? -> (reason or None, member, token payload or None)."""
        if not token:
            return "no token", 0, None
        try:
            t = rr3_attest.read_token(token_key, token)
        except ValueError as e:
            return str(e), 0, None
        with lock:
            key = attestation.player_for(t["k"])
            member = times.members.get(key, t.get("m", 0)) if key else t.get("m", 0)
        if key is None or not attestation.attested(key):
            return "not attested", member, t
        if blocklist and (blocklist.member(member) or (ip and blocklist.ip(ip))):
            return "blocked", member, t
        if build_policy and not build_policy.allows(t.get("b")):
            return "build not allowed", member, t
        return None, member, t

    def gate_verdict(token, ip):
        """v5.62 (#248): the asset gate's verdict for a token and IP, cached
        ASSET_GATE_CACHE_S. -> (reason or None, member, build, cached)."""
        if attestation is None or token_key is None or times is None:
            return "disabled", 0, "", False
        if not token:
            return "no token", 0, "", False
        now_s = time.monotonic()
        with lock:
            hit = gate_cache.get((token, ip))
        if hit and hit[0] > now_s:
            return hit[1], hit[2], hit[3], True
        reason, member, t = token_verdict(token, ip)
        build = (t or {}).get("b", "")
        with lock:
            gate_cache.pop((token, ip), None)
            gate_cache[(token, ip)] = (now_s + ASSET_GATE_CACHE_S, reason, member, build)
            while len(gate_cache) > ASSET_GATE_CACHE_MAX:
                del gate_cache[next(iter(gate_cache))]
        return reason, member, build, False

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        timeout = TIMEOUT_S

        def handle_one_request(self):
            # Whole-request deadline (v5.10): TIMEOUT_S is per read, so a
            # client sending one byte at a time could hold the thread for
            # ever; after REQUEST_S the socket is shut and the reads end.
            # v5.83 (#248): after the first request, an idle connection
            # waits at most the server's keepalive_s for the next one (was
            # TIMEOUT_S, 30 s: idle phones held every slot); parse_request
            # puts TIMEOUT_S back once a request line has come.
            keepalive = getattr(self.server, "keepalive_s", None)
            if keepalive and getattr(self, "served", 0):
                self.connection.settimeout(keepalive)
            self.t0 = None
            timer = threading.Timer(REQUEST_S, self.deadline)
            timer.daemon = True
            timer.start()
            try:
                super().handle_one_request()
            finally:
                timer.cancel()
            self.served = getattr(self, "served", 0) + 1
            if self.t0 is not None:                 # v5.83: the request's time and its wait for the lock
                ms = (time.monotonic() - self.t0) * 1000
                lock_ms = lock.take_wait() * 1000
                what = f"{self.command} {self.log_path()}"
                if hasattr(self.server, "note_request"):
                    self.server.note_request(ms, lock_ms, what)
                if ms >= SLOW_MS:
                    print(f"[----] {datetime.datetime.now().strftime('%H:%M:%S.%f')[:12]} slow: {what} "
                          f"from {self.client_address[0]} took {ms:.0f} ms (lock wait {lock_ms:.0f} ms)",
                          flush=True)

        def parse_request(self):
            self.t0 = time.monotonic()              # v5.83: the request line is in
            lock.take_wait()
            if self.timeout is not None:
                self.connection.settimeout(self.timeout)
            return super().parse_request()

        def log_path(self):
            """The path for the timing lines: no query (a login code), no key."""
            p = (getattr(self, "path", "") or "").split("?")[0]
            for pre in ("/save/", "/ghost/"):
                if p.startswith(pre):
                    return pre + "..."
            return "/rr3/live/..." if p.startswith("/rr3/live/") else p[:80]

        def deadline(self):
            self.timed_out = True
            self.close_connection = True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        def end_headers(self):
            # v5.44 (#359): one place, so every /prr/ answer (even 403, 413) has them.
            if re.sub(r"/+", "/", self.path or "").startswith(WEB_PREFIX):
                for k, v in NO_FRAME_HEADERS:
                    self.send_header(k, v)
            # v5.83 (#248): --keepalive-s 0 closes every connection after its answer
            if getattr(self.server, "keepalive_s", None) == 0 and not self.close_connection:
                self.send_header("Connection", "close")
            super().end_headers()

        def body_limit(self):
            """v5.40: syncs may be up to SYNC_MAX_BODY, everything else MAX_BODY;
            v5.63: a cloud save PUT up to saves.max_bytes (#501)."""
            if saves and self.command == "PUT" and self.path.startswith("/save/"):
                return saves.max_bytes
            return SYNC_MAX_BODY if self.command == "POST" and self.path.split("?")[0] == "/CC_Sync.php" else MAX_BODY

        def read_body(self):
            """The request body, at most body_limit() bytes (else BadBody)."""
            limit = self.body_limit()
            if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
                body = bytearray()
                while True:
                    try:
                        size = int(self.rfile.readline(1024).split(b";")[0].strip() or b"0", 16)
                    except ValueError:
                        raise BadBody(400)
                    if size < 0:
                        raise BadBody(400)
                    if size == 0:
                        for _ in range(100):
                            if self.rfile.readline(1024) in (b"\r\n", b"\n", b""):
                                break
                        break
                    if len(body) + size > limit:
                        raise BadBody(413)
                    body += self.rfile.read(size)
                    self.rfile.readline(1024)
                return bytes(body)
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                raise BadBody(400)
            if n < 0:
                raise BadBody(400)
            if n > limit:
                raise BadBody(413)
            return self.rfile.read(n) if n else b""

        def handle_any(self):
            if self.path.split("?")[0] == ASSET_GATE_PATH:     # v5.62 (#248): before the body is read
                self.asset_gate()
                return
            try:
                body = self.read_body()
                if getattr(self, "timed_out", False):
                    raise BadBody(408)              # cut off at REQUEST_S: drop it, answer nothing
            except BadBody as e:
                if e.args[0] == 408:
                    print(f"[----] {self.command} {self.path} from {self.client_address[0]}: "
                          f"not complete within {REQUEST_S} s, dropped", flush=True)
                    self.close_connection = True
                    return
                ua = (self.headers.get("User-Agent") or "-")[:120]
                print(f"[----] {self.command} {self.path} from {self.client_address[0]}: "
                      f"body refused ({e.args[0]}; length {self.headers.get('Content-Length') or 'chunked'}; "
                      f"ua {ua})", flush=True)
                self.close_connection = True
                self.send_response(e.args[0])
                self.send_header("Content-Length", "0")
                self.send_header("Connection", "close")
                self.end_headers()
                return
            with lock:
                count[0] += 1
                i = count[0]
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", self.path.strip("/"))[:60] or "root"
            now = datetime.datetime.now().isoformat(timespec="milliseconds")
            # Friends site requests are never saved: their URL and cookie log a player in.
            web = friends is not None and self.path.startswith(WEB_PREFIX)
            rule = blocklist.ip(web_client_ip(self.client_address[0], self.headers)) if blocklist else None
            if rule:
                # v5.37 (#332): a blocked address gets 403 for everything, before anything is stored (or saved)
                print(f"[{i:04d}] {now[11:]} {self.command} {self.path.split('?')[0]} from "
                      f"{web_client_ip(self.client_address[0], self.headers)}: blocked ({rule}) -> 403", flush=True)
                self.send_response(403)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            base = (os.path.join(outdir, f"{i:04d}-{self.command}-{safe}")
                    if outdir and not web and not self.path.startswith(WEB_PREFIX)
                    and not self.path.startswith("/save/") else None)   # v5.58; v5.63: never a save
            if base:
                with open(base + ".bin", "wb") as f:
                    f.write(body)
                with open(base + ".txt", "w") as f:
                    f.write(f"time: {now}\nfrom: {self.client_address[0]}\n")
                    f.write(f"request: {self.command} {self.path} {self.request_version}\n\n")
                    for k, v in self.headers.items():
                        f.write(f"{k}: {v}\n")
                    f.write(f"\nbody bytes: {len(body)}\nfirst 64 bytes: {body[:64].hex(' ')}\n")
            reply, info = None, ""
            if self.command in ("GET", "POST") and self.path.split("?")[0] == "/time":
                # Server time (v5.14, issue #197): cc::ServerTimeManager takes
                # strtod of X-Request-Start (Unix seconds); the body is not read.
                t = time.time()
                print(f"[{i:04d}] {now[11:]} {self.command} /time -> {t:.3f}", flush=True)
                self.send_response(200)
                self.send_header("X-Request-Start", f"{t:.3f}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if self.path.split("?")[0] in (ATTEST_PREFIX, ATTEST_PREFIX + "/challenge"):
                self.attest(i, now, body)
                return
            if self.path.split("?")[0] == ATT_CHECK_PATH:
                self.att_check(i, now, body)
                return
            if assets and self.command in ("GET", "HEAD") and \
                    re.sub(r"/+", "/", self.path).startswith(ASSET_PREFIX):
                # Asset update list and pack (v5.31, #292), sent here by devel's Caddy route.
                # v5.62 (#248): the same gate as /rr3/live/* (log only unless --asset-gate-enforce).
                g_reason, g_member, g_build, g_cached = gate_verdict(
                    (self.headers.get("X-PRR-Att") or "").strip(), web_client_ip(self.client_address[0], self.headers))
                g_note = (f" gate member {g_member} build {g_build or '-'}: {g_reason or 'ok'}"
                          + (" (cached)" if g_cached else "") + ("" if asset_gate_enforce else " (log only)"))
                if g_reason and asset_gate_enforce:
                    print(f"[{i:04d}] {now[11:]} {self.command} {self.path}{g_note}"
                          f" ua {self.headers.get('User-Agent', '-')!r} -> 403", flush=True)
                    out = json.dumps({"ok": False, "reason": g_reason}).encode()
                    self.send_response(403)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(out)))
                    self.end_headers()
                    if self.command == "GET":
                        self.wfile.write(out)
                    return
                with lock:
                    data = assets.get(self.path)
                    LIVE_SEEN[0].seen(g_member, None, time.time())  # v5.69 (#522): member from the token
                if data is None:
                    print(f"[{i:04d}] {now[11:]} {self.command} {self.path}{g_note} -> 404", flush=True)
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                rng = self.headers.get("Range")
                part = byte_range(rng, len(data)) if rng else None
                if rng and part is None:
                    print(f"[{i:04d}] {now[11:]} {self.command} {self.path} Range {rng} -> 416", flush=True)
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{len(data)}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                start, end = part or (0, len(data) - 1)
                out = data[start:end + 1]
                print(f"[{i:04d}] {now[11:]} {self.command} {self.path}"
                      + (f" Range {rng}" if rng else "") + f" -> {206 if part else 200}, {len(out)} bytes"
                      + f" ua {self.headers.get('User-Agent', '-')!r}{g_note}", flush=True)
                self.send_response(206 if part else 200)
                if part:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                if self.command == "GET":
                    self.wfile.write(out)
                return
            if web:
                # Friends site login and API (v5.16, issue #218). Not saved
                # with --save: the URL holds a login code.
                u = urllib.parse.urlsplit(self.path)
                ip = web_client_ip(self.client_address[0], self.headers)
                with lock:
                    reset = friends.apply_resets(times.by_member) if friends else ""
                    if results:
                        results.settle_due(time.time())
                    code, extra, data, info = web_answer(
                        self.command, u.path, urllib.parse.parse_qs(u.query), self.headers, body, ip,
                        times, friends, blocklist=blocklist, store=results, hidden=hidden or (),
                        limiter=limiter, track_names=track_names(schedule), car_names=car_names)
                if code == CLOUDSAVE_DEFER:     # v5.72 (#530): outside the lock
                    code, data, sinfo = cloudsave_answer(saves, data["member"], data["what"], body)
                    info += f": {sinfo}"
                if reset:
                    print(f"[{i:04d}] {now[11:]} {reset}", flush=True)
                print(f"[{i:04d}] {now[11:]} {self.command} {u.path} from {ip}: {info} -> {code}", flush=True)
                out = json.dumps(data).encode() if data is not None else b""
                self.send_response(code)
                for k, v in extra.items():
                    self.send_header(k, v)
                if data is not None:
                    self.send_header("Content-Type", "application/json")
                if "Cache-Control" not in extra:      # v5.47: public results say max-age=30 (#359 R8)
                    self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)
                return
            if saves and self.command == "GET" and self.path.startswith("/save/"):
                # v5.65 (#514): a restore download, the stored bytes unchanged;
                # read and sent outside the server lock; pinned once fully sent.
                skey = self.path[len("/save/"):].split("?")[0]
                with lock:
                    rule = blocklist.member(saves.restore_member(skey)) if blocklist else None
                    if not rule:                # v5.69 (#522): any request of a known player
                        LIVE_SEEN[0].seen(saves.restore_member(skey), None, time.time())
                if rule:
                    code, data, sinfo, pin = 403, None, f"blocked ({rule})", None
                else:
                    code, data, sinfo, pin = saves.get(skey, build_policy)
                self.send_response(code)
                if data is not None:
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data) if data is not None else 0))
                self.end_headers()
                sent = data is None
                try:
                    if data is not None:
                        self.wfile.write(data)
                        self.wfile.flush()
                        sent = True
                except OSError as e:
                    sinfo += f"; send failed ({e.__class__.__name__}), not pinned"
                if pin and sent:
                    sinfo += "; " + saves.pin(*pin)
                print(f"[{i:04d}] {now[11:]} GET save: {sinfo} -> {code}", flush=True)
                return
            if saves and self.command == "PUT" and self.path.startswith("/save/"):
                # v5.63 (#501): a cloud save upload, stored as received; the
                # file is written outside the server lock.
                skey = self.path[len("/save/"):].split("?")[0]
                with lock:
                    rule = blocklist.member(saves.slot_member(skey)) if blocklist else None
                    if not rule:                # v5.69 (#522)
                        LIVE_SEEN[0].seen(saves.slot_member(skey), None, time.time())
                if rule:
                    code, sinfo = 403, f"blocked ({rule})"
                else:
                    code, sinfo = saves.put(skey, body, build_policy)
                print(f"[{i:04d}] {now[11:]} PUT save {len(body)} bytes: {sinfo} -> {code}", flush=True)
                self.send_response(code)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if ghosts and self.command == "PUT" and self.path.startswith("/ghost/"):
                with lock:
                    slot = ghosts.slots.get(self.path[len("/ghost/"):].split("?")[0]) or {}
                    rule = blocklist.member(slot.get("member")) if blocklist else None
                    if not rule:                # v5.69 (#522)
                        LIVE_SEEN[0].seen(slot.get("member"), None, time.time())
                    code = 403 if rule else ghosts.put(self.path[len("/ghost/"):].split("?")[0], body, build_policy)
                if rule:
                    print(f"[{i:04d}] {now[11:]} PUT ghost {len(body)} bytes: blocked ({rule}) -> 403", flush=True)
                print(f"[{i:04d}] {now[11:]} PUT ghost {len(body)} bytes -> {code}", flush=True)
                self.send_response(code)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if times and body:
                try:
                    plain, _ = blob.unwrap(body)  # outside the lock: slow for a large body
                    if blocklist:               # v5.37 (#332): a blocked member, before anything is stored
                        with lock:
                            member = times.members.get(player_key(plain, times.server_key))
                        rule = blocklist.member(member)
                        if rule:
                            print(f"[{i:04d}] {now[11:]} {self.command} {self.path} {len(body)} bytes: "
                                  f"blocked ({rule}) -> 403", flush=True)
                            self.send_response(403)
                            self.send_header("Content-Length", "0")
                            self.end_headers()
                            return
                    subs, build, cached, allowed, source = None, None, False, True, ""
                    if build_policy:            # the decision is rr3_build_policy.BuildGate's (#242)
                        subs = blob.subsyncs(plain)
                        ua = user_agent_tag(self.headers.get("User-Agent"))     # v5.28 (#272)
                        tag68 = blob.build_tag(plain, subs)
                        if ua is not None:      # the User-Agent wins over 68
                            allowed, build, cached = build_policy.check(
                                player_key(plain, times.server_key), ua, True)
                            source = " (ua)" + (f" (68 said {tag68})" if tag68 and tag68 != ua else "")
                        else:
                            allowed, build, cached = build_policy.check(
                                player_key(plain, times.server_key), tag68,
                                any(t == 68 for t, _t2, _z, _p in subs))
                            source = " (cached)" if cached else " (68)" if build else ""
                    if build_policy and not allowed:
                        info = f" build {build or 'unknown'}{source} denied"
                        if build is None:       # v5.41 (#299): what did it send instead of a tag?
                            types = ",".join(str(t) for t, _t2, _z, _p in (subs or []))
                            info += (f" (ua {(self.headers.get('User-Agent') or '-')[:100]}; subsyncs {types or '-'}; "
                                     f"68 {blob.report_head(plain, subs) or '-'}; "
                                     f"ids {' '.join(blob.header(plain)['shapes']) or 'none'})")
                        print(f"[{i:04d}] {now[11:]} {self.command} {self.path} {len(body)} bytes{info}",
                              flush=True)
                        self.send_response(403)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    if token_key is not None:   # v5.58 (#452): the build goes into the player's token
                        with lock:
                            remember_build(player_key(plain, times.server_key), build)
                    exempt = False
                    if attest_enforce:          # v5.57 (#452): only attested players
                        key = player_key(plain, times.server_key)
                        exempt = (attest_ios_exempt and not attestation.attested(key)
                                  and ios_exempt(blob.header(plain), build if build_policy else None))
                        if not attestation.attested(key) and not exempt:
                            with lock:
                                keep_pending(key, blob.header(plain)["secret"])
                                member = times.members.get(key, 0)
                            why = ""
                            if attest_ios_exempt and build and IOS_BUILD_RE.match(build):   # v5.61 (#451)
                                h = blob.header(plain)
                                ids = h["shapes"] + [x for x in ("android_id", "synergy_id") if h[x]]
                                why = (f" (ios: {ios_exempt_why(h, build) or 'attested?'}; "
                                       f"ids {' '.join(ids) or 'none'})")
                            print(f"[{i:04d}] {now[11:]} {self.command} {self.path} {len(body)} bytes "
                                  f"member {member}: att {attestation.label(key)} denied"
                                  + (f" build {build}{source}" if build_policy else "") + why, flush=True)
                            self.send_response(403)
                            self.send_header("Content-Length", "0")
                            self.end_headers()
                            return
                    if build_policy and build_policy.admit_file is not None:   # v5.23 (#242); v5.57: after attestation
                        build_policy.admit_file.add(
                            ip_key(web_client_ip(self.client_address[0], self.headers)), build)
                    apk = apk_label(blob.header(plain)["sig"], trusted)
                    shadow = apk.startswith("other") if times.shadow_other else None
                    info = " apk " + apk + (" (shadowed)" if shadow else "")
                    if attestation is not None:     # v5.38 (#204): log only
                        info += " att " + attestation.label(player_key(plain, times.server_key)) \
                            + (" (ios exempt)" if exempt else "")
                    if build_policy:
                        info += f" build {build}{source}"
                    with lock:
                        reply, names = answer_for(body, times, ghosts,
                                                  self.headers.get("Host") or "%s:%d" % self.server.server_address[:2],
                                                  schedule, plain, self.client_address[0], shadow, friends, build,
                                                  subs, assets, saves)
                    info += f" subsyncs {names}" + (" -> ANSWERED" if reply else "")
                except Exception as e:      # keep recording whatever happens
                    info = f" (decode failed: {e})"
                    if saves and "over the limit" in str(e):     # v5.63 (#501): a corrupt-save report?
                        types = peek_subsync_types(body)
                        info += (" (subsyncs seen: " + (",".join(map(str, types)) or "none")
                                 + ("; corrupt-save report 22 refused for size" if 22 in types else "") + ")")
            print(f"[{i:04d}] {now[11:]} {self.command} {self.path} {len(body)} bytes{info}", flush=True)
            if reply:
                if base:
                    with open(base + "-reply.bin", "wb") as f:
                        f.write(reply)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)
                return
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def attest(self, i, now, body):
            """Key attestation endpoints (v5.38, #204): never saved with --save."""
            path = self.path.split("?")[0]

            def send(code, data=None, info=""):
                out = json.dumps(data).encode() if data is not None else b""
                print(f"[{i:04d}] {now[11:]} {self.command} {path}{info} -> {code}", flush=True)
                self.send_response(code)
                if data is not None:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            if attestation is None or times is None:
                return send(503, None, ": attestation disabled")
            if path.endswith("/challenge"):
                if self.command != "GET":
                    return send(405)
                return send(200, {"v": 1, "nonce": attestation.new_nonce()})
            if self.command != "POST":
                return send(405)
            if len(body) > ATTEST_BODY_MAX:
                return send(413)
            try:
                nonce, aid, chain = rr3_attest.parse_request(body)
            except ValueError as e:
                return send(400, {"ok": False, "reason": "bad request"}, f": bad request ({e})")
            key = private_player_key(times.server_key, "a", aid)
            with lock:
                secret = (friends.secrets.get(key) if friends else None) or pending.get(key)
                member = times.members.get(key, 0)
                LIVE_SEEN[0].seen(member, None, time.time())    # v5.69 (#522): any request of a known player
            if not secret:                  # v5.57 (#452): 503, so PrrAttest tries again after its sync
                return send(503, {"ok": False, "reason": "no secret"}, f" member {member}: no secret yet")
            r = attestation.check(nonce, secret, chain)
            if r["bound"]:                  # only a proof tied to the player's secret changes their state
                attestation.record(key, r)
            label = attestation.label(key) if r["bound"] else f"fail ({r['reason']}), not recorded"
            answer = {"ok": True} if r["ok"] else {"ok": False, "reason": r["reason"]}
            if r["ok"] and token_key is not None:   # v5.58 (#452): a token for other servers
                with lock:
                    build = last_build.get(key, "")
                answer["token"] = rr3_attest.make_token(token_key, {
                    "m": member, "k": key[2:18], "b": build, "l": r["level"], "s": r["key"],
                    "exp": int(r["time"] + attestation.ttl_s)})
                label += " (token)"
            send(200, answer, f" member {member}: att {label}")

        def att_check(self, i, now, body):
            """POST ATT_CHECK_PATH (v5.58, #452): is this attestation token
            good now? For devel's asset server, with X-PRR-Admin. Never saved."""
            def send(code, data, info):
                out = json.dumps(data).encode()
                print(f"[{i:04d}] {now[11:]} {self.command} {ATT_CHECK_PATH}{info} -> {code}", flush=True)
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            if attestation is None or token_key is None or admin_key is None or times is None:
                return send(503, {"ok": False, "reason": "disabled"}, ": disabled")
            if self.command != "POST":
                return send(405, {"ok": False, "reason": "method"}, "")
            given = (self.headers.get("X-PRR-Admin") or "").strip().encode()
            if not hmac.compare_digest(given, base64.b64encode(admin_key)):
                return send(401, {"ok": False, "reason": "admin key"}, ": wrong X-PRR-Admin")
            if len(body) > ATT_CHECK_BODY_MAX:
                return send(413, {"ok": False, "reason": "too large"}, "")
            try:
                req = json.loads(body)
                token, sig, ip = req.get("token") or "", req.get("sig") or "", req.get("ip") or ""
                if not all(isinstance(x, str) for x in (token, sig, ip)):
                    raise ValueError
            except (ValueError, AttributeError):
                return send(400, {"ok": False, "reason": "bad request"}, ": bad request")
            note = f" sig {sig[:8] or '-'}" + (f" ip {ip}" if ip else "")

            def no(reason, who=""):
                return send(403, {"ok": False, "reason": reason}, f"{who}{note}: {reason}")

            reason, member, t = token_verdict(token, ip)
            who = f" member {member}" if t else ""
            if reason == "build not allowed":
                who += f" build {t.get('b') or '-'}"
            if reason:
                return no(reason, who)
            with lock:
                LIVE_SEEN[0].seen(member, None, time.time())    # v5.69 (#522)
            send(200, {"ok": True, "member": member, "build": t.get("b", ""), "level": t.get("l"),
                       "signer": t.get("s"), "exp": t["exp"]},
                 f"{who} build {t.get('b') or '-'}{note}: ok")

        def asset_gate(self):
            """GET ASSET_GATE_PATH (v5.62, #248 option B): Caddy's forward_auth
            asks whether a /rr3/live/* or /assetman/* request may go on to
            devel's asset server. 204 = yes, 403 = no (only with
            --asset-gate-enforce; else every verdict is only logged). The body
            is never read and the connection is closed."""
            with lock:
                count[0] += 1
                i = count[0]
            now = datetime.datetime.now().isoformat(timespec="milliseconds")
            self.close_connection = True
            peer = self.client_address[0]
            if peer not in ("127.0.0.1", "::1"):
                print(f"[{i:04d}] {now[11:]} asset gate from {peer}: not this machine -> 403", flush=True)
                self.send_response(403)
                self.send_header("Content-Length", "0")
                self.send_header("Connection", "close")
                self.end_headers()
                return
            h = self.headers
            uri = re.sub(r"/+", "/", h.get("X-Forwarded-Uri") or "")
            ip = web_client_ip(peer, h)
            if not uri.startswith(ASSET_GATE_PREFIXES):
                reason, member, build, cached = "bad uri", 0, "", False
            else:
                reason, member, build, cached = gate_verdict((h.get("X-PRR-Att") or "").strip(), ip)
            code = 403 if reason and asset_gate_enforce else 204
            print(f"[{i:04d}] {now[11:]} asset gate {h.get('X-Forwarded-Method') or '-'} {uri[:160] or '-'} "
                  f"from {ip} member {member} build {build or '-'} sig {(h.get('X-PRR-Sig') or '-')[:8]} "
                  f"ua {(h.get('User-Agent') or '-')[:300]!r}: {reason or 'ok'}"
                  + (" (cached)" if cached else "") + ("" if asset_gate_enforce else " (log only)")
                  + f" -> {code}", flush=True)
            self.send_response(code)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            if code == 403:
                out = json.dumps({"ok": False, "reason": reason}).encode()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)
                return
            if member:
                self.send_header("X-PRR-Member", str(member))
                with lock:
                    LIVE_SEEN[0].seen(member, None, time.time())    # v5.69 (#522)
            self.end_headers()

        do_POST = do_GET = do_PUT = do_HEAD = handle_any

        def log_message(self, *args):
            pass

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--bind", default="127.0.0.1",
                    help="address to listen on: 127.0.0.1 (default) = this device only, "
                         "0.0.0.0 = also other devices, for a server on a PC")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"),
                    help="folder for the saved requests (default logs/ next to this script)")
    ap.add_argument("--status", type=int, default=503, help="HTTP status sent back (default 503)")
    ap.add_argument("--max-connections", type=int, default=MAX_CONNECTIONS,
                    help=f"connections handled at once; more are closed (default {MAX_CONNECTIONS})")
    ap.add_argument("--keepalive-s", type=float, default=KEEPALIVE_S, metavar="S",
                    help=f"v5.83 (#248): after a request, wait at most S seconds for the connection's next "
                         f"one, then close it (default {KEEPALIVE_S}; 0 = close after every answer; was "
                         f"{TIMEOUT_S}, which let idle phones hold every slot)")
    ap.add_argument("--listen-queue", type=int, default=LISTEN_QUEUE, metavar="N",
                    help=f"v5.83 (#248): listen backlog (default {LISTEN_QUEUE}; was Python's 5; "
                         f"the kernel caps it at net.core.somaxconn)")
    ap.add_argument("--per-ip", type=int, default=PER_IP, metavar="N",
                    help="v5.83 (#248): phone connections one IP may have open at once; more are closed "
                         "at once (default 0 = no cap; players behind one carrier NAT share an IP)")
    ap.add_argument("--local-connections", type=int, default=LOCAL_CONNECTIONS,
                    help=f"connections from this machine (Caddy: the asset gate, proxied asset and site "
                         f"requests) handled at once, apart from --max-connections; 0 = share "
                         f"--max-connections as before v5.81 (default {LOCAL_CONNECTIONS}; #248)")
    ap.add_argument("--answer", action="store_true",
                    help="answer leaderboards, race results and ghosts (needs rr3_cc_blob.py)")
    ap.add_argument("--name", help="name for every player not in --names and without a username "
                                   "(for a server only you use); default: Racer + last 4 characters "
                                   "of the player key")
    ap.add_argument("--names", help="JSON file {\"<Android id, Synergy id or player key>\": \"<name>\"}, "
                                    "read again on every request")
    ap.add_argument("--tag", default="PRR", help="team tag shown as [TAG] (default PRR)")
    ap.add_argument("--times", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-leaderboard.json"),
                    help="file with the stored best times (default data/rr3-leaderboard.json "
                         "next to this script)")
    ap.add_argument("--usernames", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-usernames.json"),
                    help="file with the players' in-game usernames (rr3_username.py), by player key")
    ap.add_argument("--username-claims", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-username-claims.json"),
                    help="v5.74 (#178): which member holds each username (built from --usernames when missing)")
    ap.add_argument("--members", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-members.json"),
                    help="file with each player's member id, by player key (ids are never reused)")
    ap.add_argument("--server-key", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.key"),
                    help="secret for the player keys (created on the first start with --answer); "
                         "keep it private and back it up: a new one makes every player new")
    ap.add_argument("--ghosts", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ghosts"),
                    help="folder for the players' Time Trial ghost files")
    ap.add_argument("--ghost-url", help="start of the ghost upload URL the phones get, for example "
                                        "https://lb.example.org (default: http:// + the request's Host header)")
    ap.add_argument("--cloud-save", action="store_true",
                    help="cloud save backups, phase (a) of #501 (v5.63): answer the upload slot (10660) "
                         "and done (10661), take PUT /save/<key> and keep corrupt-save reports (22); "
                         "off by default. Lists (47) get an empty list (v5.64), downloads (48) stay "
                         "unanswered; needs --answer")
    ap.add_argument("--cloud-save-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "saves"),
                    metavar="DIR", help="folder for the saves, by member id (private; default data/saves)")
    ap.add_argument("--cloud-save-max-bytes", type=int, default=SAVE_MAX, metavar="N",
                    help=f"largest save upload accepted (default {SAVE_MAX}, 9 MB)")
    ap.add_argument("--cloud-save-versions", type=int, default=SAVE_VERSIONS, metavar="N",
                    help=f"saves kept per member, newest first (default {SAVE_VERSIONS}; a pinned one is extra)")
    ap.add_argument("--cloud-save-presets", metavar="FILE",
                    help="v5.72 (#530): JSON {\"presets\": [{\"id\", \"name\", \"file\"}]} of preset "
                         "character.2.dat files (paths relative to FILE) that logged-in members can pick "
                         "on the site's Cloud save page; needs --cloud-save")
    ap.add_argument("--cloud-save-restore-all", action="store_true",
                    help="v5.73 (#530): every member gets restores of their own cloud saves in the game "
                         "(not iOS builds yet); the tester file and site opt-ins work as before; needs --cloud-save")
    ap.add_argument("--cloud-save-restore", metavar="FILE",
                    help="cloud save restore, phase (b) of #501 (#514, v5.65): the member ids in FILE (one per "
                         "line, # comments, read again when it changes) get their newest stored version in the "
                         "game's Cloud Save screen and can download it (GET /save/<key>); needs --cloud-save")
    ap.add_argument("--mail", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-mail.json"),
                    help="file with the players' \"someone beat your time\" mail")
    ap.add_argument("--rivals", action="store_true", help="ignored since v5.30 (the test drivers are gone); kept so old start commands work")
    ap.add_argument("--skip-queued", action="store_true",
                    help="accept each player's first upload without storing it when it holds more "
                         "than one result (results queued so far)")
    save = ap.add_mutually_exclusive_group()
    save.add_argument("--save", action="store_true",
                      help="save every request in --out (bodies and headers hold phone ids); "
                           "for your own tests only")
    save.add_argument("--no-save", action="store_true",
                      help="save nothing (the default since v5.1; kept for old command lines)")
    ap.add_argument("--omp-invites", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-omp-invites.json"),
                    help="OMP invites from the hosts' 10455 (v5.56, #427; private: holds the pass keys; "
                         "rr3_mp_server.py --invites reads it; default data/rr3-omp-invites.json)")
    ap.add_argument("--omp-private-rooms", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-omp-private-rooms.json"),
                    help="the open private rooms rr3_mp_server.py v0.24 writes (--private-rooms); an "
                         "invite for a room not in it is refused (v5.56, #427)")
    ap.add_argument("--omp-selector-rooms", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-omp-selector-rooms.json"),
                    help="the locked Race Selector P2P rooms rr3_mp_server.py v0.26 writes (--selector-rooms): "
                         "their StartMatch gets the room's track and laps, unranked (v5.60, #469)")
    ap.add_argument("--news", metavar="FILE",
                    help="server-side popup broadcast: answer the news room sync 10748 with the messages in "
                         "this JSON file for the players they target (re-read when it changes; example "
                         "tools/rr3-news.example.json; v5.85, #644)")
    ap.add_argument("--news-test", metavar="FILE",
                    help="answer the news room sync 10748 from this JSON test file, for the members it lists "
                         "(read at every request; example tools/rr3-news-test.example.json; v5.55, #427)")
    ap.add_argument("--prize-test", action="append", metavar="MEMBER:EVENTS",
                    help="answer subsync 10781 (competition prize winners) for this member id (or all) with "
                         "these event ids, e.g. 1001:82870 or all:82870; repeatable; for tests (v5.39, #193)")
    ap.add_argument("--prize-events", metavar="FILE",
                    help="WTT prize table (rr3_wtt_dates.py prizes): answer 10781 with the WTTs each member "
                         "has a time in that ended within --prize-days, each once (v5.76, #193)")
    ap.add_argument("--prize-days", type=int, default=PRIZE_DAYS,
                    help=f"days an ended WTT stays in the prize list (default {PRIZE_DAYS})")
    ap.add_argument("--prize-sent", metavar="FILE",
                    help="record of the events already sent to each member "
                         "(default prize-sent.json next to --times)")
    ap.add_argument("--asset-update", metavar="DIR",
                    help="offer the files under DIR (DIR/data/events.dat.nct = /data/events.dat.nct) as "
                         "an asset update: answer 10449 and serve /rr3/live/asset_list_updates* (v5.31, #292)")
    ap.add_argument("--asset-update-ios", action="store_true",
                    help="offer the asset update (10449) to iPhones too; since v5.66 they get none "
                         "(an IDFV or a PRR iNN build label), so they never fetch our files")
    ap.add_argument("--asset-test", metavar="DIR",
                    help="a second asset update for the members in --asset-testers only: they get this "
                         "set instead of --asset-update's (v5.35, #311); DIR must hold every file they need")
    ap.add_argument("--asset-testers", metavar="FILE",
                    help="member ids that get --asset-test, one per line (# comments), read again when "
                         "it changes (v5.35, #311)")
    ap.add_argument("--omp", help="answer the online multiplayer schedule (10536) from this JSON "
                                  "file (see rr3-omp-schedule.example.json); needs --answer")
    ap.add_argument("--omp-data", help="the phone's data/onlinemp.dat, decrypted with rr3_nct.py: "
                                       "check the schedule's car-group keys at start-up")
    ap.add_argument("--omp-rating-test", action="store_true",
                    help="FinishedMatch rows send rating before / after 1217 / 1234 (+17) for the first "
                         "player, 996 / 987 (-9) for the second (others 1000 / 1000 + index) instead of "
                         "1000 / 1000, to see where the results screen shows them (v5.43, issue #262; "
                         "before / after since v5.67, #521)")
    ap.add_argument("--ratings", choices=RATINGS_MODES, default="off",
                    help="OMP ratings (v5.79, #263): off = none; shadow = rated into the shadow files only, "
                         "never sent or shown (turns on by itself at --ratings-start); on = rated, sent in "
                         "FinishedMatch and shown on the site. Default off")
    ap.add_argument("--ratings-start", metavar="YYYY-MM-DD",
                    help="the day ratings start (shown on the site); with --ratings shadow, ratings turn "
                         "on at 00:00 UTC that day with no restart (v5.79, #263; Tom 2026-11-09: the "
                         "release + 7 days)")
    ap.add_argument("--ratings-file", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-omp-ratings.json"),
                    help="the real OMP ratings, written in on (v5.79; default data/rr3-omp-ratings.json)")
    ap.add_argument("--ratings-shadow-file", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-omp-ratings-shadow.json"),
                    help="the shadow ratings (v5.79; default data/rr3-omp-ratings-shadow.json); one line "
                         "per rated room goes to the same name ending in .jsonl")
    ap.add_argument("--ratings-report", metavar="RATINGS_JSON",
                    help="print the top / bottom players and the largest swings (from the file's .jsonl "
                         "room log, if any) of a ratings file, then exit; names with --answer (v5.79)")
    ap.add_argument("--omp-matches", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-omp-matches.json"),
                    help="open (not yet settled) OMP matches, reloaded at start (v5.47, #360; "
                         "default data/rr3-omp-matches.json next to this script)")
    ap.add_argument("--omp-results", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-omp-results.jsonl"),
                    help="settled OMP races, one JSON record per line, appended once (v5.47, #360; "
                         "default data/rr3-omp-results.jsonl next to this script)")
    ap.add_argument("--omp-leagues", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-omp-leagues.json"),
                    help="OMP league picks and the league each member was last served (v5.48, #264; "
                         "default data/rr3-omp-leagues.json next to this script; rr3_mp_server.py --leagues "
                         "reads it)")
    ap.add_argument("--mp-status", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "mp-status.json"),
                    help="rr3_mp_server.py's --status-file (v0.28), only read: lobby rooms for "
                         "/prr/api/live and MP counts for /prr/api/status; missing or older than 60 s = "
                         "none (v5.71, #542, #374; default data/mp-status.json next to this script)")
    ap.add_argument("--public-hidden", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "public-hidden.txt"),
                    help="admin: members shown as \"Player\" on the public results pages, one `member N` per "
                         "line, re-read when it changes (v5.47, #359 R6; default data/public-hidden.txt)")
    ap.add_argument("--lb-banned", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "lb-banned.txt"),
                    metavar="FILE",
                    help="admin: leaderboard ban (v5.80, #607), one `member N` per line, # for the reason, "
                         "re-read when it changes: the member still plays and sees their own times, their "
                         "friends still see them, nobody else does; no WTT prize (default data/lb-banned.txt)")
    ap.add_argument("--lb-testers", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "lb-testers.txt"),
                    help="team testers, `member N` per line, re-read when it changes: their times are shown to "
                         "them and their PRR friends only and earn no WTT prize (v5.84, #606; default data/lb-testers.txt)")
    ap.add_argument("--lb-admins", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "lb-admins.txt"),
                    help="members who may use the admin page (held results), `member N` per line, re-read when it "
                         "changes (v5.84, #606; default data/lb-admins.txt)")
    ap.add_argument("--lb-floors", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "lb-floors.csv"),
                    help="minimum lap times per track (CSV kind,key,floor_ms: tt by track name, omp by track id), "
                         "re-read when it changes: a Time Trial time under it is held (t3), an OMP time under laps x it "
                         "is DNF (v5.86, #606; default data/lb-floors.csv; missing = no floors)")
    ap.add_argument("--event-index", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "event-index.csv"),
                    help="the repo's tables/event-index.csv (event -> track), for the Time Trial floors (v5.86)")
    ap.add_argument("--floors-suggest", metavar="OUT_CSV",
                    help="write a suggested --lb-floors table (0.9 x the fastest trusted lap per track, 5+ trusted "
                         "times) to OUT_CSV, read-only on the stores, then exit (v5.86, #606)")
    ap.add_argument("--no-lb-holds", action="store_true",
                    help="turn the hold rules off: new bests are shown at once, as before v5.84 (#606)")
    ap.add_argument("--held-report", action="store_true",
                    help="print every held time (who, event, time, why, the field) with the approve/reject lines, "
                         "read-only, then exit (v5.84, #606)")
    ap.add_argument("--lb-banned-report", action="store_true",
                    help="print what each member in --lb-banned and --blocklist has stored (times, ghosts, "
                         "OMP races, prizes), read-only, then exit (v5.80)")
    ap.add_argument("--omp-groups", metavar="ONLINEMP_DAT",
                    help="print the car groups of a decrypted onlinemp.dat with car names, then exit")
    ap.add_argument("--events", metavar="EVENT_INDEX_CSV",
                    help="store results and ghosts only for the events in this file (the repo's "
                         "tables/event-index.csv, column event_id); default: any event")
    ap.add_argument("--cars", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "car-index.csv"),
                    metavar="CAR_INDEX_CSV",
                    help="the game's car ids (the repo's tables/car-index.csv, column car_id): results, "
                         "leaderboard rows and ghosts with another car are refused (v5.45; default "
                         "data/car-index.csv next to this script; a missing file only checks car >= 0)")
    ap.add_argument("--no-cars", action="store_true",
                    help="do not check car ids against a car list (only car >= 0, as before v5.45)")
    ap.add_argument("--new-players-per-ip", type=int, default=NEW_PLAYERS_PER_IP, metavar="N",
                    help=f"new players one IP may add per hour; more are refused (default "
                         f"{NEW_PLAYERS_PER_IP}, 0 = no cap; behind a reverse proxy every phone "
                         f"has the proxy's IP)")
    ap.add_argument("--trusted-sigs", metavar="FILE",
                    help="trusted APK signing keys, one 'name SHA256' per line (# comments), e.g. "
                         "'devel 546c...' and 'tom db89...'; requests from a key are logged \"apk <name>\"; "
                         "re-read when the file changes; needs --answer")
    ap.add_argument("--trusted-sig", action="append", default=[], metavar="SHA256",
                    help="SHA-256 of a trusted APK signing certificate, as keytool or "
                         "apksigner print it; repeatable. Requests from it are logged \"apk trusted\" "
                         "(name keys with --trusted-sigs); needs --answer")
    ap.add_argument("--build-allowlist", metavar="FILE",
                    help="enforce Cloudcell sync and ghost-upload access for exact PRR build labels in this "
                         "UTF-8 file (one `PRR bNN-channel` or iOS `PRR iNN-channel` per line; missing/unknown labels are denied); "
                         "file reloads about once a second; needs --answer")
    ap.add_argument("--build-admit-file", metavar="FILE",
                    help="also write the IP of every allowed sync to this JSON file (15 min), for servers "
                         "that see no build label (asset downloads, rr3_build_policy.AdmitFile); "
                         "needs --build-allowlist")
    ap.add_argument("--shadow-other", action="store_true",
                    help="hide the times, ghosts and mail of players whose latest request is from an "
                         "APK not signed by a --trusted-sig key from everyone else (needs --trusted-sig)")
    ap.add_argument("--blocklist", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "blocklist.txt"),
                    metavar="FILE",
                    help="players (member N) and addresses (ip A.B.C.D or A.B.C.0/24) refused with 403, "
                         "one per line, # for the reason; re-read when it changes; a missing file blocks "
                         "nobody (default data/blocklist.txt next to this script; v5.37, #332)")
    ap.add_argument("--no-attest", action="store_true",
                    help="turn off key attestation (v5.38, #204; on by default with --answer when the "
                         "cryptography package is installed)")
    ap.add_argument("--attest-enforce", action="store_true",
                    help="refuse syncs (403) from players without a passing key attestation in the last 24 h; "
                         "without working attestation CC does not start (v5.57, #452)")
    ap.add_argument("--attest-ios-exempt", action="store_true",
                    help="with --attest-enforce, still answer iPhones (IDFV, no Android id, a player secret, an "
                         "allowed PRR iNN build label) that can't attest; logged \"att none (ios exempt)\" "
                         "(v5.59, #451). Anyone sending such a header gets through")
    ap.add_argument("--asset-gate-enforce", action="store_true",
                    help="refuse (403) asset requests that fail the gate at " + ASSET_GATE_PATH
                         + " (Caddy forward_auth for devel's asset server) and CC's own asset_list_updates; "
                           "without it every verdict is only logged. Needs key attestation (v5.62, #248)")
    ap.add_argument("--att-token-key", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "prr-att.key"),
                    metavar="FILE", help="key that signs attestation tokens, base64, made on first start (private, 0600; "
                                         "default data/prr-att.key; v5.58, #452)")
    ap.add_argument("--att-admin-key", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "prr-admin.key"),
                    metavar="FILE", help="secret another server sends as X-PRR-Admin to " + ATT_CHECK_PATH
                                         + ", base64, made on first start (private, 0600; default data/prr-admin.key)")
    ap.add_argument("--attest-state", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-attest.json"),
                    metavar="FILE", help="each player's latest attestation result (private; default data/rr3-attest.json)")
    ap.add_argument("--attest-status", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "attest-status.json"),
                    metavar="FILE", help="cache of Google's attestation revocation list, refreshed daily "
                                         "(default data/attest-status.json)")
    ap.add_argument("--shadowed", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-shadowed.json"),
                    help="file with the shadowed players' keys (--shadow-other)")
    ap.add_argument("--secrets", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-secrets.json"),
                    help="file with each player's secret from the game (issue #218; the first one "
                         "sent is kept): private (mode 0600), back it up, never under a web folder")
    ap.add_argument("--friends", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-friends.json"),
                    help="file with the friends and friend requests made on the website (issue #218)")
    ap.add_argument("--friend-details", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-friend-details.json"),
                    help="each player's own stats and owned cars from their 10472 request, shown to their "
                         "friends (v5.53, issue #278)")
    ap.add_argument("--secret-resets", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-secret-resets.txt"),
                    help="admin reset file (v5.25, issue #163): member ids, one per line; the next request "
                         "drops their secrets and website sessions and empties the file")
    ap.add_argument("--secret-reset-requests", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rr3-secret-reset-requests.json"),
                    help="reset requests filed by a wrong login code made with the phone's newer secret "
                         "(v5.54, issue #423; private, mode 0600): an admin approves one by adding the member "
                         "id to --secret-resets, and that secret is kept")
    a = ap.parse_args()
    PRIZE_TEST.update(parse_prize_test(a.prize_test))
    if a.prize_events:
        if a.prize_days < 1:
            sys.exit("--prize-days must be at least 1")
        PRIZES[0] = PrizeList(a.prize_events, a.prize_sent or os.path.join(os.path.dirname(os.path.abspath(a.times)),
                                                                           "prize-sent.json"), a.prize_days)
        if not PRIZES[0].events:
            sys.exit(f"--prize-events {a.prize_events}: {PRIZES[0].load() or 'no events'}")
    NEWS_TEST[0] = a.news_test
    if a.news:                                      # v5.85 (#644)
        NEWS[0] = NewsBroadcast(a.news)
        NEWS[0].refresh()
    ASSET_UPDATE_IOS[0] = a.asset_update_ios        # v5.66
    OMP_RATING_TEST[0] = a.omp_rating_test
    if a.max_connections < 1:
        sys.exit("--max-connections must be at least 1")
    if a.local_connections < 0:
        sys.exit("--local-connections must be 0 or more")
    if a.keepalive_s < 0 or a.keepalive_s > TIMEOUT_S:
        sys.exit(f"--keepalive-s must be from 0 to {TIMEOUT_S}")
    if a.listen_queue < 1:
        sys.exit("--listen-queue must be at least 1")
    if a.per_ip < 0:
        sys.exit("--per-ip must be 0 or more")
    if a.new_players_per_ip < 0:
        sys.exit("--new-players-per-ip must be 0 or more")
    events = None
    if a.events:
        try:
            with open(a.events, newline="") as f:
                events = frozenset(int(r["event_id"]) for r in csv.DictReader(f))
        except (OSError, KeyError, ValueError) as e:
            sys.exit(f"--events {a.events}: not an event list with an event_id column ({e})")
        if not events:
            sys.exit(f"--events {a.events}: no events")
    cars, cars_note = None, " (car ids not checked: --no-cars)"
    if not a.no_cars:
        try:
            cars = load_cars(a.cars)
            cars_note = f" (car list: {len(cars)} cars)"
        except FileNotFoundError:
            cars_note = f" (WARNING: car ids not checked, {a.cars} not found; copy tables/car-index.csv there)"
        except (OSError, KeyError, ValueError) as e:
            sys.exit(f"--cars {a.cars}: not a car list with a car_id column ({e})")
    if a.omp_groups:
        names = {}
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tables", "car-index.csv")) as f:
                names = {int(r["car_id"]): r["name"] for r in csv.DictReader(f)}
        except FileNotFoundError:
            pass
        try:
            groups = omp_groups(a.omp_groups)
        except (OSError, ValueError, struct.error) as e:
            sys.exit(str(e))
        for key, cars in groups.items():
            print(f"{key}: " + ", ".join(f"{c} {names.get(c, '?')}" for c in cars))
        return 0
    if a.omp and not a.answer:
        sys.exit("--omp needs --answer")
    if (a.trusted_sig or a.trusted_sigs) and not a.answer:
        sys.exit("--trusted-sig/--trusted-sigs needs --answer")
    if a.build_allowlist and not a.answer:
        sys.exit("--build-allowlist needs --answer")
    if a.cloud_save and not a.answer:
        sys.exit("--cloud-save needs --answer")
    if a.cloud_save_restore_all and not a.cloud_save:
        sys.exit("--cloud-save-restore-all needs --cloud-save")
    if a.cloud_save_presets and not a.cloud_save:
        sys.exit("--cloud-save-presets needs --cloud-save")
    if a.cloud_save_restore and not a.cloud_save:
        sys.exit("--cloud-save-restore needs --cloud-save")
    if a.cloud_save_max_bytes < 1 or a.cloud_save_versions < 1:
        sys.exit("--cloud-save-max-bytes and --cloud-save-versions must be at least 1")
    if a.shadow_other and not (a.trusted_sig or a.trusted_sigs):
        sys.exit("--shadow-other needs --trusted-sigs or --trusted-sig (else every signed APK, devel's too, is 'other')")
    if (a.trusted_sig or a.trusted_sigs) and blob is None:
        sys.exit("--trusted-sig needs rr3_cc_blob.py next to this script")
    if a.build_admit_file and not a.build_allowlist:
        sys.exit("--build-admit-file needs --build-allowlist")
    if a.build_allowlist and blob is None:
        sys.exit("--build-allowlist needs rr3_cc_blob.py next to this script")
    cli = [trusted_digest(t) for t in a.trusted_sig]
    if None in cli:
        sys.exit("--trusted-sig takes a SHA-256: 64 hex digits (colons allowed)")
    try:
        trusted = TrustedSigs(cli, a.trusted_sigs)
    except (OSError, ValueError) as e:
        sys.exit(str(e))
    try:
        build_policy = (BuildGate(BuildAllowlist(a.build_allowlist),
                                  admit_file=AdmitFile(a.build_admit_file) if a.build_admit_file else None)
                        if a.build_allowlist else None)
    except (OSError, ValueError) as e:
        sys.exit(str(e))
    try:
        schedule = load_schedule(a.omp, omp_groups(a.omp_data) if a.omp_data else None) if a.omp else None
    except (OSError, ValueError, struct.error) as e:
        sys.exit(str(e))
    blocklist = Blocklist(a.blocklist)
    def boxlog(t):
        print(f"[----] {datetime.datetime.now().strftime('%H:%M:%S.%f')[:12]} {t}", flush=True)
    lb_banned = HiddenList(a.lb_banned, label="lb-banned", diff=True, actions=True, log=boxlog)
    lb_testers = HiddenList(a.lb_testers, label="lb-testers", diff=True, log=boxlog)     # v5.84 (#606)
    lb_admins = HiddenList(a.lb_admins, label="lb-admins", diff=True, log=boxlog)        # v5.84 (#606)
    if a.floors_suggest:                # v5.86 (#606): read-only on the stores; writes OUT only
        try:
            print(floors_suggest(a.times, a.members, a.ghosts, a.event_index, a.omp_results, a.floors_suggest,
                                 set(lb_banned.members) | set(lb_testers.members)
                                 | set(getattr(blocklist, "_members", ()))))
        except OSError as e:
            sys.exit(f"--floors-suggest: {e}")
        return 0
    FLOORS[0] = Floors(a.lb_floors, a.event_index, log=boxlog)                          # v5.86 (#606)
    if a.held_report:                   # v5.84 (#606): read-only, like --lb-banned-report
        print(held_report(a.times, a.members, a.usernames, a.ghosts, lb_banned.members,
                          lb_testers.members, getattr(blocklist, "_members", ())))
        return 0
    if a.lb_banned_report:              # v5.80 (#607): read-only, before anything opens the stores
        lb = {m: "lb-banned" for m in lb_banned.members}
        for m in getattr(blocklist, "_members", ()):     # rr3_build_policy v1.3 has no public list
            lb.setdefault(m, "blocklist")
        print(lb_banned_report(sorted(lb.items()), a.members, a.usernames, a.times, a.ghosts, a.omp_results,
                               a.prize_sent or os.path.join(os.path.dirname(os.path.abspath(a.times)),
                                                            "prize-sent.json")))
        return 0
    attestation, att_note = None, ""
    if a.answer and not a.no_attest:
        if rr3_attest is None or not rr3_attest.AVAILABLE:
            att_note = " (attestation disabled: " + (rr3_attest.WHY_NOT if rr3_attest else "rr3_attest.py missing") + ")"
        else:
            attestation = rr3_attest.Attestation(a.attest_state, rr3_attest.RevocationList(a.attest_status),
                                                 trusted.get)
            att_note = (f" (key attestation v{rr3_attest.VERSION}, "
                        + ("ENFORCED" + (", iPhones exempt" if a.attest_ios_exempt else "")
                           if a.attest_enforce else "log only") + "; revocation list: "
                        + (f"{len(attestation.revocation)} entries" if attestation.revocation.loaded
                           else "fetching") + ")")
            attestation.revocation.maybe_refresh()
    token_key = admin_key = None
    if attestation is not None:     # v5.58 (#452): tokens for other servers, checked at ATT_CHECK_PATH
        try:
            token_key = rr3_attest.load_key_file(a.att_token_key)
            admin_key = rr3_attest.load_key_file(a.att_admin_key)
        except (OSError, ValueError) as e:
            sys.exit(f"--att-token-key / --att-admin-key: {e}")
        att_note = att_note[:-1] + f"; tokens, check at {ATT_CHECK_PATH})"
    if a.attest_ios_exempt and not (a.attest_enforce and a.build_allowlist):    # v5.59 (#451)
        sys.exit("--attest-ios-exempt needs --attest-enforce and --build-allowlist (it exempts allowed iOS labels)")
    if a.asset_gate_enforce and token_key is None:  # v5.62 (#248): fail closed, as --attest-enforce
        sys.exit("--asset-gate-enforce needs key attestation: --answer, no --no-attest, and rr3_attest.py "
                 "with the cryptography package" + att_note)
    if a.attest_enforce and attestation is None:    # v5.57 (#452): fail closed, never a silent "off"
        sys.exit("--attest-enforce needs key attestation: --answer, no --no-attest, and rr3_attest.py "
                 "with the cryptography package" + att_note)
    server_key = load_server_key(a.server_key) if a.answer else None
    if a.answer and blob is None:
        sys.exit("--answer needs rr3_cc_blob.py next to this script")
    if a.save:
        os.makedirs(a.out, exist_ok=True)
    times = Times(a.times, a.name, a.tag, a.rivals, a.skip_queued, a.names, server_key,
                  a.usernames, a.members, Mail(a.mail), events, a.new_players_per_ip,
                  a.shadowed, a.shadow_other, cars, a.username_claims) if a.answer else None
    if a.ratings_report:                # v5.79 (#263): the shadow week check
        log = os.path.splitext(a.ratings_report)[0] + ".jsonl"

        def name(m):
            key = times.by_member.get(m) if times else None
            return times.display_name(key) if key else "?"
        try:
            print(ratings_report(a.ratings_report, log if os.path.exists(log) else None, name))
        except (OSError, ValueError, KeyError, TypeError) as e:
            sys.exit(f"--ratings-report {a.ratings_report}: {e}")
        return 0
    ghosts = Ghosts(a.ghosts, a.ghost_url, events, cars) if a.answer else None
    saves = (CloudSaves(a.cloud_save_dir, a.ghost_url, a.cloud_save_max_bytes, a.cloud_save_versions,
                        MemberFile(a.cloud_save_restore) if a.cloud_save_restore else None,
                        load_presets(a.cloud_save_presets) if a.cloud_save_presets else None,
                        a.cloud_save_restore_all)
             if a.cloud_save else None)
    friends = (Friends(a.secrets, a.friends, a.secret_resets, a.friend_details, a.secret_reset_requests)
               if a.answer else None)
    if times is not None:               # v5.80 (#607)
        times.lb_banned, times.blocklist, times.friends = lb_banned, blocklist, friends
        times.testers, times.admins, times.holds = lb_testers, lb_admins, not a.no_lb_holds     # v5.84 (#606)
        times.ghosts = ghosts
        times.wtt = PRIZES[0].window if PRIZES[0] is not None else None
        acted, released = times.apply_actions(), times.recheck_all()
        if acted or released:
            boxlog(f"held times: {acted} approved/rejected from {a.lb_banned}, {released} released at start")
    results = hidden = None
    car_names = {}
    if a.answer:
        try:
            results = OmpStore(a.omp_matches, a.omp_results, server_key)
        except OSError as e:
            sys.exit(f"--omp-matches / --omp-results: {e}")
        OMP_STORE[0] = results
        try:                            # v5.79 (#263)
            OMP_RATINGS[0] = OmpRatings(a.ratings_file, a.ratings_shadow_file,
                                        os.path.splitext(a.ratings_shadow_file)[0] + ".jsonl",
                                        a.ratings, a.ratings_start)
        except (OSError, ValueError, TypeError, AttributeError) as e:
            sys.exit(f"--ratings / --ratings-start / --ratings-file: {e}")
        OMP_LEAGUES[0] = OmpLeagues(a.omp_leagues)
        OMP_INVITES[0] = OmpInvites(a.omp_invites, a.omp_private_rooms)
        OMP_SELECTOR[0] = OmpSelectorRooms(a.omp_selector_rooms)
        hidden = HiddenList(a.public_hidden)
        MP_STATUS[0] = MpStatus(a.mp_status)    # v5.71 (#542, #374)
        LIVE_SEEN[0].since = time.time()
        if not a.no_cars:
            try:
                car_names = load_car_names(a.cars)
            except (OSError, KeyError, ValueError):
                car_names = {}

        def settle_timer():
            next_live = time.time() + LIVE_LOG_S
            mode = OMP_RATINGS[0].mode_at(time.time())
            while True:
                time.sleep(SETTLE_TICK_S)
                with lock:
                    if OMP_RATINGS[0].mode_at(time.time()) != mode:     # v5.79 (#263): --ratings-start reached
                        mode = OMP_RATINGS[0].mode_at(time.time())
                        print(f"[----] {datetime.datetime.now().strftime('%H:%M:%S.%f')[:12]} ratings: now {mode} "
                              f"(--ratings-start {OMP_RATINGS[0].start}); rooms that started before stay "
                              "unranked", flush=True)
                    results.settle_due(time.time())
                    if time.time() >= next_live:        # v5.68 (#522): once a minute
                        next_live = time.time() + LIVE_LOG_S - 1     # the 15 s tick: about every 60 s
                        print(f"[----] {datetime.datetime.now().strftime('%H:%M:%S.%f')[:12]} live: "
                              + live_log(results, LIVE_SEEN[0], time.time()), flush=True)
        threading.Thread(target=settle_timer, daemon=True).start()
    srv = CappedHTTPServer((a.bind, a.port),
                           make_handler(a.out if a.save else None, a.status, times, ghosts, schedule, trusted,
                                        friends, build_policy,
                                        AssetSets(a.asset_update, a.asset_test, a.asset_testers)
                                        if (a.asset_update or a.asset_test) and a.answer else None,
                                        blocklist, attestation, results, hidden, car_names,
                                        attest_enforce=a.attest_enforce, token_key=token_key,
                                        admin_key=admin_key, attest_ios_exempt=a.attest_ios_exempt,
                                        asset_gate_enforce=a.asset_gate_enforce, saves=saves),
                           a.max_connections, a.local_connections,
                           listen_queue=a.listen_queue, keepalive_s=a.keepalive_s, per_ip=a.per_ip)
    srv.start_stats()                           # v5.83 (#248): the "slots:" line once a minute
    where = f"saving requests in {a.out}" if a.save else "not saving requests (--save to keep copies)"
    print(f"rr3_cc_server.py v{VERSION}. Listening on http://{a.bind}:{a.port}/, {where}"
          + (" (answering leaderboards, results, ghosts and the friends site " + WEB_PREFIX + ")"
             if a.answer else "")
          + (" (and the OMP schedule, leagues in " + a.omp_leagues + ")" if schedule else "")
          + (f" (prize test: {PRIZE_TEST})" if PRIZE_TEST else "")
          + (f" (prize list: {len(PRIZES[0].events)} WTTs, {PRIZES[0].days} days)" if PRIZES[0] else "")
          + (f" (news: {NEWS[0].path}, {len(NEWS[0].messages)} message(s))" if NEWS[0] is not None else "")
          + (f" (news test: {NEWS_TEST[0]})" if NEWS_TEST[0] else "")
          + (" (OMP rating test columns)" if OMP_RATING_TEST[0] else "")
          + (f" (asset update from {a.asset_update}" + (", iPhones too" if a.asset_update_ios else ", not iPhones")
             + ")" if a.asset_update and a.answer else "")
          + (f" ({len(trusted)} trusted APK signature(s): {trusted.names()}"
             + (", shadowing the others" if a.shadow_other else "") + ")" if len(trusted) else "")
          + (f" (build allowlist: {build_policy.count} build(s))" if build_policy else "")
          + (f" (cloud save backups in {a.cloud_save_dir}: {a.cloud_save_versions} per member, "
             f"at most {a.cloud_save_max_bytes} bytes"
             + (f"; restore for the members in {a.cloud_save_restore}" if a.cloud_save_restore else "")
             + (f"; {len(saves.presets)} preset(s) on the site" if saves and a.cloud_save_presets else "")
             + ("; restore for every member (not iOS)" if a.cloud_save_restore_all else "")
             + ")" if saves else "")
          + (f" (OMP results: {len(results.records)} settled, {len(results.open)} open; "
             f"{len(hidden.members)} hidden)" if results else "")
          + (f" (OMP ratings: {OMP_RATINGS[0].mode}"
             + (f", now {OMP_RATINGS[0].mode_at(time.time())}"
                if OMP_RATINGS[0].mode_at(time.time()) != OMP_RATINGS[0].mode else "")
             + (f", start {a.ratings_start}" + (" 00:00 UTC (on by itself)" if a.ratings == "shadow" else "")
                if a.ratings_start else "")
             + f"; {len(OMP_RATINGS[0].tables['on'])} rated)" if results else "")
          + f" (blocklist: {blocklist.describe()})"
          + (f" (lb-banned: {len(lb_banned.members)} member(s))" if a.answer else "")
          + (f" (held results: {'off' if a.no_lb_holds else 'on'}, {len(times.held_list())} held; "
             f"lb-testers: {len(lb_testers.members)}; lb-admins: {len(lb_admins.members)}; "
             f"floors: {len(FLOORS[0].tt)} TT, {len(FLOORS[0].omp)} OMP)" if a.answer else "") + att_note
          + (f" (asset gate at {ASSET_GATE_PATH}: " + ("ENFORCED" if a.asset_gate_enforce else "log only") + ")"
             if a.answer else "")
          + (f" (slots: {a.max_connections} remote, {a.local_connections} local" if a.local_connections
             else f" (slots: {a.max_connections}, shared")
          + f"; keep-alive {a.keepalive_s:g} s; listen queue {a.listen_queue}"
          + (f"; per-IP cap {a.per_ip}" if a.per_ip else "") + ")"
          + (cars_note if a.answer else "")
          + (f" ({len(events)} known events)" if events else "") + " (Ctrl+C to stop)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print(f"\nStopped. {count[0]} request(s)" + (f" saved in {a.out}" if a.save else ""))


if __name__ == "__main__":
    sys.exit(main())
