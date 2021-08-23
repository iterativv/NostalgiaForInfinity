#!/bin/bash

# CREATE A STRATEGY FOR EACH BUY

########################################## CONFIG ##########################################

originalStrategyName="NostalgiaForInfinityNext"
numberOfBuyCondition=46

########################################## VERIFICATIONS ##########################################

originalStrategyFile="$originalStrategyName.py"

if [ ! -e "$originalStrategyFile" ]; then
  echo "/!\ $originalStrategyFile not found /!\\"
  exit 1
fi

########################################### GO ##########################################

# we disable each by on the original strategy
for i in $(seq 1 $numberOfBuyCondition); do
  sed -i "s/\"buy_condition_${i}_enable\": True,/\"buy_condition_${i}_enable\": False,/g" "$originalStrategyFile"
done

# we create a strategy for each buy
for i in $(seq 1 $numberOfBuyCondition); do
  newStrategyName="${originalStrategyName}Buy${i}"
  newStrategyFile="${newStrategyName}.py"
  cp "$originalStrategyFile" "$newStrategyFile"
  sed -i "s/$originalStrategyName/$newStrategyName/g" "$newStrategyFile"
  sed -i "s/\"buy_condition_${i}_enable\": False,/\"buy_condition_${i}_enable\": True,/g" "$newStrategyFile"
  printf '%s ' "$newStrategyName"
done
printf "\n"

# we re-enable each by on the original strategy
for i in $(seq 1 $numberOfBuyCondition); do
  sed -i "s/\"buy_condition_${i}_enable\": False,/\"buy_condition_${i}_enable\": True,/g" "$originalStrategyFile"
done

echo "Done!"
