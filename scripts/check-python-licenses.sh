#!/bin/sh
set -eu

cd "$(dirname "$0")/../server"

# SPDX 标识与 pip-licenses 的 Trove 名称均限于仓库已允许的许可族。
exec .venv/bin/pip-licenses --from=mixed --ignore-packages knowledge-server \
  --allow-only="MIT;MIT License;BSD;BSD License;BSD-2-Clause;BSD-3-Clause;Apache-2.0;Apache Software License;ISC;ISC License (ISCL);PSF;PSF-2.0;Python-2.0;Python Software Foundation License;MPL-2.0;Mozilla Public License 2.0 (MPL 2.0);W3C-20150513;MIT AND PSF-2.0;Apache-2.0 OR BSD-2-Clause"
