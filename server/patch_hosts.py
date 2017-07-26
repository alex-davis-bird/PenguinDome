#!/usr/bin/env python3

import argparse
import os

from qlmdm import set_gpg, signatures_dir
from qlmdm.server import patch_hosts, get_db, get_logger

log = get_logger('patch_hosts')
set_gpg('server')


def parse_args():
    parser = argparse.ArgumentParser(description='Add, modify, or remove a '
                                     'file on one or more hosts')
    subparsers = parser.add_subparsers()

    parser.add_argument('--host', action='append', default=[], help='Host(s) '
                        'to patch (default is all)')

    patch_parser = subparsers.add_parser('patch', help='Add or replace a file',
                                         aliases=('add', 'cp'))
    patch_parser.set_defaults(func=patch_handler)
    patch_parser.add_argument(
        '--mode', type=lambda m: int(m, 8),
        help='Mode for patched file (specify in octal, default 0755)')
    patch_parser.add_argument('target_path', help='Relative path of file on '
                              'destination')
    patch_parser.add_argument('source_file', help='Local file containing '
                              'patch content')

    rm_parser = subparsers.add_parser('remove', help='Remove a file',
                                      aliases=('rm',))
    rm_parser.set_defaults(func=rm_handler)
    rm_parser.add_argument('target_path', help='Relative path of file on '
                           'destination')

    ls_parser = subparsers.add_parser('list', help='List pending patches',
                                      aliases=('ls',))
    ls_parser.set_defaults(func=ls_handler)

    cancel_parser = subparsers.add_parser('cancel', help='Cancel a pending '
                                          'patch')
    cancel_parser.set_defaults(func=cancel_handler)
    cancel_parser.add_argument('target_path', help='Relative path of file on '
                               'destination')

    args = parser.parse_args()
    # Uniquify
    args.host = list(set(args.host))

    if 'func' not in args:
        parser.error('No subcommand specified')

    return args


def patch_handler(args):
    kwargs = {}
    if args.mode:
        kwargs['patch_mode'] = args.mode
    kwargs['patch_content'] = open(args.source_file, 'rb').read()
    kwargs['hosts'] = args.host if args.host else None
    patch_hosts(args.target_path, **kwargs)


def rm_handler(args):
    patch_hosts(args.target_path,
                patch_mode=0,
                hosts=args.host if args.host else None)


def file_descriptions(patch):
    sig_prefix = signatures_dir + os.sep

    for f in patch['files']:
        if f['path'].startswith(sig_prefix):
            continue
        d = ''
        d += 'patch ' if f['mode'] else 'remove '
        d += f['path']
        if f['mode']:
            d += ' [mode 0{:o}]'.format(f['mode'])
        yield d


def ls_handler(args):
    db = get_db()
    spec = {}
    if args.host:
        spec['pending_hosts'] = {'$in': args.host}
    else:
        spec['pending_hosts'] = {'$gt': []}

    for patch in db.patches.find(spec):
        pending_hosts = ', '.join(sorted(patch['pending_hosts']))
        for f in file_descriptions(patch):
            print('{} pending on {}'.format(f, pending_hosts))


def cancel_handler(args):
    db = get_db()
    spec = {'files.path': args.target_path}
    if args.host:
        spec['pending_hosts'] = {'$in': args.host}
    else:
        spec['pending_hosts'] = {'$gt': []}
    for patch in db.patches.find(spec):
        pending_hosts = patch['pending_hosts']
        remove_hosts = args.host if args.host else pending_hosts
        remaining_hosts = set(pending_hosts) - set(remove_hosts)
        removed_hosts = set(pending_hosts) - set(remaining_hosts)
        hosts_list = ', '.join(sorted(removed_hosts))
        for f in file_descriptions(patch):
            print('Canceling {} on {}'.format(f, hosts_list))
        db.patches.update({'_id': patch['_id']},
                          {'$set': {'pending_hosts': list(remaining_hosts)}})


def main():
    args = parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
