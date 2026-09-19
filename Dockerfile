# The Commish: a fantasy football agent on Plow, built on plow-pbc/plow-hermes-agent.
# Base pinned by digest (same as life-assistant-hermes-agent); bump tag and digest together.
FROM public.ecr.aws/e1h7x4a2/plow-cloud-agents:base-ef0019372ff8bca593611b31ebd2e08f9f1458ff@sha256:a8a2f97ad78b8192d80a984dce81d3bf5a9a883d18cb7b677704913a09b56aee

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

# Agent Index usage reporter: the base's own (pinned client + s6 "agent-index"
# longrun, every 5 minutes). It reads AGENT_ID; the Plow cloud passes no
# environment, so the id is baked here. Compose sets the same value.
ENV AGENT_ID=the-commish
