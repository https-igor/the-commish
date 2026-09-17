# The Commish: a fantasy football agent on Plow, built on plow-pbc/plow-hermes-agent.
# Base pinned by digest (same as life-assistant-hermes-agent); bump tag and digest together.
FROM public.ecr.aws/e1h7x4a2/plow-cloud-agents:base-51f83158a70a383f03a4d03dbd8b6ea102cf0361@sha256:253d7ed3409effa7fa59113d93b4b79bb731d8264cdaf4cd60294924d0110a2e

# Identity: plow-init composes SOUL.md on every boot as the base persona + this file.
COPY runtime/persona.md /opt/hermes/plow-seed/persona.md
RUN chmod 0644 /opt/hermes/plow-seed/persona.md
COPY LICENSE /usr/share/doc/the-commish/

# Skills, shipped outside the home; the base runtime reconciles them into it.
COPY skills/ /opt/hermes/skills/
RUN find /opt/hermes/skills -mindepth 1 -type d -exec chmod 0755 {} + \
 && find /opt/hermes/skills -mindepth 1 -type f ! -perm -u+x -exec chmod 0644 {} + \
 && find /opt/hermes/skills -mindepth 1 -type f -perm -u+x -exec chmod 0755 {} +

# Root-owned copy of the tool for the unattended injury monitor, out of the agent's reach.
COPY skills/commish-coach/scripts/commish.py /opt/commish/commish.py
RUN chmod 0755 /opt/commish && chmod 0644 /opt/commish/commish.py

# The Commish's state: linked Sleeper account and feed caches.
RUN install -d -o 10000 -g 10000 -m 0700 /var/lib/hermes/commish

# Agent Index usage reporter (copied from life-assistant-hermes-agent): the client
# is fetched at the commit vendor/client.pin names and checked against its sha256.
COPY vendor/client.pin /opt/plow/agent-index-client.pin
RUN set -eu; \
    sha="$(sed -n 's/^sha=//p' /opt/plow/agent-index-client.pin)"; \
    want="$(sed -n 's/^sha256=//p' /opt/plow/agent-index-client.pin)"; \
    path="$(sed -n 's/^path=//p' /opt/plow/agent-index-client.pin)"; \
    curl -fsS --max-time 60 -o /opt/plow/agent-index-client.py \
      "https://raw.githubusercontent.com/plow-pbc/agent-index-client/${sha}/${path}"; \
    got="$(sha256sum /opt/plow/agent-index-client.py | cut -d' ' -f1)"; \
    [ "$got" = "$want" ] || { echo "agent-index client is $got, pin says $want" >&2; exit 1; }; \
    chown -R root:root /opt/plow; chmod 0755 /opt/plow; chmod 0644 /opt/plow/*

# s6 longrun "agent-index": depends on plow-init, reports every 5 minutes.
COPY image/s6-overlay/ /etc/s6-overlay/
RUN chmod 0755 /etc/s6-overlay/s6-rc.d/agent-index/run
