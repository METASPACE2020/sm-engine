#!/usr/bin/env python
import argparse
import pika
import json

from sm.engine.util import SMConfig


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Script for adding messages to the job queue')
    parser.add_argument('ds_id', type=str, help='Dataset name')
    parser.add_argument('input_path', type=str, help='Path to a dataset location')
    parser.add_argument('--config', dest='sm_config_path', default='conf/config.json', type=str, help='SM config path')

    args = parser.parse_args()
    SMConfig.set_path(args.sm_config_path)
    rabbit_config = SMConfig.get_conf()['rabbitmq']

    creds = pika.PlainCredentials(rabbit_config['user'], rabbit_config['password'])
    conn = pika.BlockingConnection(pika.ConnectionParameters(host=rabbit_config['host'], credentials=creds))

    ch = conn.channel()
    ch.queue_declare(queue='sm_annotate')

    m = {
        'ds_name': args.ds_name,
        'input_path': args.input_path
    }

    ch.basic_publish(exchange='', routing_key='sm_annotate', body=json.dumps(m))
    print(" [v] Sent '{}'".format(json.dumps(m)))
    conn.close()
