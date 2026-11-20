# Phone notifications

## Idea

Send pipeline updates to the user's phone when a session stops (waiting for the human, blocked,
paused with reset time, finished), naming the app and the reason, from the agent's Stop and
Notification hooks. Replies: plain text, `/clear`, `/bull:resume` or `/bull:status` only, typed into
the app's tmux session by a relay on the Mac. Security: outbound polling only, owner's account only,
input only while the session is idle. bull's first network service. Shares the waiting state and
tmux sessions with the GUI. Details: `docs/gui.md` § Related. Open: channel (Telegram bot preferred,
email the alternative); whether finished long steps also notify.

## Discussion notes

## Agreed scope
