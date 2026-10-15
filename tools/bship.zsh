# Add to ~/.zshrc:
#   source "${BSHIP_REPO:-$HOME/programing/ha-2n-intercom}/tools/bship.zsh"
# Set BSHIP_REPO to use a different checkout; it must be on main.

bship() {
  emulate -L zsh
  local msg="${1:-Backlog update}" br changes doctor_output

  cd -- "${BSHIP_REPO:-$HOME/programing/ha-2n-intercom}" || return 1
  if [[ "$(git symbolic-ref --quiet --short HEAD)" != main ]]; then
    print -u2 -- "bship: checkout must be on main."
    return 1
  fi
  if ! changes="$(git status --porcelain --untracked-files=all -- . ':!backlog' ':!docs')"; then
    print -u2 -- "bship: could not inspect checkout changes."
    return 1
  fi
  if [[ -n "$changes" ]]; then
    print -u2 -- "bship: changes outside backlog/ and docs/:"
    print -ru2 -- "$changes"
    return 1
  fi
  if ! git pull --ff-only; then
    print -u2 -- "bship: pull failed; resolve it on main before retrying."
    return 1
  fi
  if ! doctor_output="$(backlog doctor 2>&1)"; then
    print -ru2 -- "$doctor_output"
    print -u2 -- "bship: backlog doctor failed. For duplicate IDs, run backlog doctor --fix and review the repair."
    return 1
  fi
  print -r -- "$doctor_output"
  if [[ "$doctor_output" != 'No duplicate task IDs found in active or completed tasks.' ]]; then
    print -u2 -- "bship: backlog doctor did not report a clean result. Run backlog doctor --fix and review the repair."
    return 1
  fi

  br="backlog-$(date +%Y%m%d-%H%M%S)"
  if ! { git switch -c "$br" && git add -- backlog docs && git commit -q -m "$msg"; }; then
    print -u2 -- "bship: could not create the backlog commit."
    return 1
  fi
  if ! { git push -q -u origin "$br" \
    && gh pr create --base main --title "$msg" --body "Backlog-only change." \
    && gh pr merge --merge --delete-branch; }; then
    print -u2 -- "bship: PR shipping failed; inspect the branch and PR before retrying."
    return 1
  fi
  if ! { git switch -q main && git pull -q --ff-only; }; then
    print -u2 -- "bship: PR merged, but updating main failed."
    return 1
  fi
}
