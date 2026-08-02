#!/bin/zsh
# 監測雙方命令交件：兩邊的 命令_T<n>.md 都出現才結束（裁判收到通知後解算）
# 用法：watch.sh <tick編號> [最長等待分鐘，預設 40]
N=$1
MAXMIN=${2:-40}
RED=$HOME/Desktop/料鋒_紅軍指揮部/命令_T$N.md
BLUE=/private/tmp/claude-501/-Users-ethan/cc3113fc-aaac-4221-a45c-761794239adb/scratchpad/blue_hq/命令_T$N.md
LOOPS=$((MAXMIN * 60 / 8))
i=0
while [ $i -lt $LOOPS ]; do
  r=0; b=0
  [ -s "$RED" ] && r=1
  [ -s "$BLUE" ] && b=1
  if [ $r -eq 1 ] && [ $b -eq 1 ]; then
    echo "BOTH_READY T$N  紅軍✅ 藍軍✅"
    exit 0
  fi
  i=$((i + 1))
  sleep 8
done
echo "TIMEOUT T$N  紅軍=$r 藍軍=$b （等了 ${MAXMIN} 分鐘）"
exit 1
