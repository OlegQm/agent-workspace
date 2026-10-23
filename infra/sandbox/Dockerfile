FROM nousresearch/hermes-agent@sha256:984813f70658b8ef6d78cb48a56c798c36dc1db20ac7f99cb0b5d55436f1a69b

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends sudo \
    && rm -rf /var/lib/apt/lists/* \
    && if getent passwd 1000 >/dev/null; then userdel -r "$(getent passwd 1000 | cut -d: -f1)"; fi \
    && useradd --uid 1000 --create-home --shell /bin/bash agent \
    && printf 'agent ALL=(ALL) NOPASSWD:ALL\n' >/etc/sudoers.d/agent \
    && printf 'Defaults:agent env_keep += "HTTP_PROXY HTTPS_PROXY NO_PROXY http_proxy https_proxy no_proxy"\n' >>/etc/sudoers.d/agent \
    && chmod 0440 /etc/sudoers.d/agent

RUN uv pip install --python /opt/hermes/.venv/bin/python \
      pandas==2.3.2 numpy==2.3.2 scipy==1.16.1 scikit-learn==1.7.1 \
      openpyxl==3.1.5 XlsxWriter==3.2.5 pyarrow==21.0.0 duckdb==1.3.2 \
      matplotlib==3.10.5 plotly==6.2.0 pypdf==5.9.0 python-docx==1.2.0 Pillow==11.3.0 \
    && ln -sf /opt/hermes/.venv/bin/hermes /usr/local/bin/hermes \
    && mkdir -p /home/agent/.local/bin \
    && chown -R agent:agent /home/agent

COPY start-hermes.sh /usr/local/bin/start-open-agent-workspace-hermes
RUN chmod 0755 /usr/local/bin/start-open-agent-workspace-hermes

USER agent
WORKDIR /home/agent

# Docker Sandboxes owns the microVM lifecycle. The upstream s6 entrypoint is
# intended for the standalone Hermes container and would terminate an SBX
# shell-agent before the kit-managed API server can stay available.
ENTRYPOINT []
CMD ["sleep", "infinity"]
