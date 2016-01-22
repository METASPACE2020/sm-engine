#/usr/bin/env bash
source /miniconda/bin/activate sm_distributed
export PYTHONPATH=/code/SM_distributed:/root/spark-1.6.0-bin-hadoop2.6/python:$PYTHONPATH
python scripts/run_molecule_search.py $1 /data/$2 --config /code/SM_distributed/docker/config.json
