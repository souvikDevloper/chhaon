# Test the Strands Agents engine against Bedrock (bedrock-mantle) from this PC with local AWS credentials.
$ErrorActionPreference = 'Continue'
python scripts\strands_mantle_test.py 2>&1
exit 0
