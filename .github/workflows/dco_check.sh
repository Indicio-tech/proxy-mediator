#!/usr/bin/env bash
set -eo pipefail
revs=$(git rev-list "${1:-HEAD}") || exit 1
failed=0
for commit in $revs; do
    if git show -s --format=%B "${commit}" | grep >/dev/null 2>&1 "Signed-off-by: "; then
        echo -e "\e[32m\u2714\e[0m $(git show -s --format='%h %s' $commit)"
    else
        echo -e "\e[31m\u2718 $(git show -s --format='%h %s' $commit)\e[0m"
        failed=1
    fi
done
[ $failed -eq 0 ] || exit 1
