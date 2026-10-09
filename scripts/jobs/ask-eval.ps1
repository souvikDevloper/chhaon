# Ask the live assistant real supervisor questions and print the plan beside the answers.
param([string]$Base = 'https://d2cvj3mcid9pim.cloudfront.net')
$ErrorActionPreference = 'Continue'
python scripts\ask_eval.py $Base 2>&1
exit 0
