# Deploying

GitHub `main` is the source of truth for this repo, even though the coding server serves it.
Don't push to `main` yourself. Commit on your own branch, push the branch, and open a PR with `gh pr create`. The user reviews the diff and merges it.
Merging to `main` deploys: coding pulls it within a minute and restarts the site (root livescope-update and infinitescope-update timers; a change here restarts both livescope and infinitescope).
Don't rsync or scp code to coding, edit files there, or pull and restart by hand.
A checkout on coding with local edits is skipped, not overwritten, so leave those checkouts clean.
