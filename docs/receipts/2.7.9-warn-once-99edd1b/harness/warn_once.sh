#!/usr/bin/env bash
# xrpl-lab 2.7.9 (#45): count the state-version warning per command, on one commit, against home snapshots restored to
# the SAME fixed path before every command. Item 1: feedback, support-bundle, support-bundle --json, status. Item 2: a
# state-saving dry-run module run, then status, on the same home (no restore between). Read-only against the ledger.
# Usage: warn_once.sh <ref> <label> <out-root> <name:snapshot-dir>...
set -u
REF="$1"; LABEL="$2"; OUT="$3/$LABEL"; shift 3
WT=<worktree>; LAB=$WT/.venv/Scripts/xrpl-lab.exe
PAD=<scratch>
FIX=$PAD/fb279   # the fixed path every snapshot is restored to
git -C $WT switch -q --detach "$REF" || exit 2
uv pip install -q --python $WT/.venv/Scripts/python.exe -e $WT --no-deps || exit 3
mkdir -p $OUT; echo "ref: $REF = $(git -C $WT rev-parse HEAD) | $($LAB --version)" > $OUT/code.txt
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 COLUMNS=160; unset XRPL_LAB_RPC_URL XRPL_LAB_FAUCET_URL
restore() { rm -rf $FIX && mkdir -p $FIX && cp -r $1/home $1/cwd $FIX/; }
one() {  # one <dir> <label> <args...>: run in the fixed home, record out/err/exit and the warning count
  local d=$1 l=$2; shift 2
  ( cd $FIX/cwd && yes "" | XRPL_LAB_HOME="$(cygpath -w $FIX/home)" $LAB "$@" > $d/$l.out 2> $d/$l.err; echo "exit: ${PIPESTATUS[1]}" > $d/$l.exit )
  echo "warnings on stderr: $(grep -c 'Warning: state from v' $d/$l.err) | on stdout: $(grep -c 'Warning: state from v' $d/$l.out)" >> $d/$l.exit
  echo "state.json version after: $(python -c "import json,sys;print(json.load(open(sys.argv[1]))['version'])" $FIX/home/state.json)" >> $d/$l.exit
}
for s in "$@"; do
  name=${s%%:*}; src=${s#*:}; d=$OUT/$name; mkdir -p $d
  echo "state.json version in the snapshot: $(python -c "import json,sys;print(json.load(open(sys.argv[1]))['version'])" $src/home/state.json)" > $d/snapshot.txt
  for cmd in "feedback" "support-bundle" "support-bundle --json" "status"; do
    restore $src; one $d "$(echo "$cmd" | tr ' ' '_' | tr -d -)" $cmd
  done
  restore $src
  one $d item2_1_run_dryrun run receipt_literacy --dry-run --force
  one $d item2_2_status status
  one $d item2_3_feedback feedback
done
echo "captured $LABEL"
