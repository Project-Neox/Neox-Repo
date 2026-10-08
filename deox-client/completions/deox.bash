# DEOX bash tab tamamlama
# Kurulum: /usr/share/bash-completion/completions/deox (install.sh otomatik yapar)

_deox() {
    local cur prev
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    local opts="-S -R -Q -U -Sy -Su -Syu -Syyu -Ss -Si -Qs -Qi -Ql -Qo -Sc -Scc -Rs -Rns -R -S --history --rollback --stats --doctor --export --import --clean-orphans --check-updates --add-repo --remove-repo --list-repos --vote --snapshot --version --help --json --verbose --debug --no-confirm --no-color --yes"

    # bayraklardan sonra paket adı tamamlaması gerekmez; düz liste yeterli
    COMPREPLY=($(compgen -W "$opts" -- "$cur"))
    return 0
}

complete -F _deox deox
