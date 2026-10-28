"""Generate candidate status-page hostnames from a company-name list.

usage: python3 gen_hosts.py <names_file> <out_file>
The names file is whitespace-separated company slugs, one pool per run.
"""
import sys

SUFFIXES = [
    "{}.statuspage.io", "status.{}.com", "status.{}.io", "status.{}.co",
    "status.{}.net", "status.{}.dev", "status.{}.ai", "status.{}.app",
    "{}status.com", "www.{}status.com", "status.{}.cloud", "status.{}.tech",
    "status.{}.eu", "status.{}.jp", "status.{}.ru", "status.{}.ch",
    "status.{}.nl", "status.{}.de", "status.{}.in", "status.{}.sh",
]


def main(names_file, out_file):
    names = [n.strip() for n in open(names_file).read().split() if n.strip().isalnum()]
    seen, out = set(), []
    for n in names:
        for s in SUFFIXES:
            h = s.format(n.lower())
            if h not in seen:
                seen.add(h)
                out.append(h)
    with open(out_file, 'w') as f:
        f.write('\n'.join(out) + '\n')
    print(f'{len(names)} names -> {len(out)} hosts -> {out_file}')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
