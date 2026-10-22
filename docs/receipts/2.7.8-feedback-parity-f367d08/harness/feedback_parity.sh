#!/usr/bin/env bash
# xrpl-lab: capture `feedback`, `support-bundle`, `support-bundle --json`, every command's --help, and an import probe
# of xrpl_lab.feedback, on one commit, against home snapshots restored to the SAME fixed path before every command (so
# paths cannot differ between commits). Read-only against the ledger (doctor checks only).
# Usage: feedback_parity.sh <ref> <label> <out-root>
set -u
REF="$1"; LABEL="$2"; OUT="$3/$LABEL"
WT=<worktree>; LAB=$WT/.venv/Scripts/xrpl-lab.exe; PY=$WT/.venv/Scripts/python.exe
PAD=<scratch>   # session scratch: the 2.7.7 live-check homes (with their wallets) live here and never leave it
SNAPS="leftfailed:$PAD/leftfailed-check-c99bab1-20261022T0406Z recovered:$PAD/force-check-c99bab1-20261022T0407Z"
FIX=$PAD/fb278   # the fixed path every snapshot is restored to
git -C $WT switch -q --detach "$REF" || exit 2
uv pip install -q --python $WT/.venv/Scripts/python.exe -e $WT --no-deps || exit 3
mkdir -p $OUT; echo "ref: $REF = $(git -C $WT rev-parse HEAD) | $($LAB --version)" > $OUT/code.txt
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 COLUMNS=160; unset XRPL_LAB_RPC_URL XRPL_LAB_FAUCET_URL
for s in $SNAPS; do
  name=${s%%:*}; src=${s#*:}; mkdir -p $OUT/$name
  for cmd in "feedback" "support-bundle" "support-bundle --json"; do
    rm -rf $FIX && mkdir -p $FIX && cp -r $src/home $src/cwd $FIX/
    lbl=$(echo "$cmd" | tr ' ' '_' | tr -d -)
    ( cd $FIX/cwd && XRPL_LAB_HOME="$(cygpath -w $FIX/home)" $LAB $cmd < /dev/null > $OUT/$name/$lbl.out 2> $OUT/$name/$lbl.err; echo "exit: $?" > $OUT/$name/$lbl.exit )
    # did the command change the home or workspace?
    diff -rq $src/home $FIX/home > $OUT/$name/$lbl.home-diff 2>&1; diff -rq $src/cwd $FIX/cwd > $OUT/$name/$lbl.cwd-diff 2>&1
  done
done
mkdir -p $OUT/help; $LAB --help > $OUT/help/_top.txt 2>&1
for c in $($LAB --help | sed -n '/^Commands:/,$p' | awk 'NR>1 && NF {print $1}') feedback; do $LAB $c --help > $OUT/help/$c.txt 2>&1; done
$LAB proof --help > /dev/null 2>&1; for g in proof wallet curriculum module; do for sc in $($LAB $g --help 2>/dev/null | sed -n '/^Commands:/,$p' | awk 'NR>1 && NF {print $1}'); do $LAB $g $sc --help > $OUT/help/$g.$sc.txt 2>&1; done; done
$PY -I -c "import xrpl_lab.feedback" > $OUT/import_feedback.txt 2>&1; echo "exit: $?" >> $OUT/import_feedback.txt
echo "captured $LABEL"
