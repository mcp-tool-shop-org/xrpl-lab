#!/usr/bin/env node
"use strict";

// Pure JSON config — npm-launcher derives asset names from convention:
//   binary:    xrpl-lab-1.7.1-linux-x64
//   checksums: checksums-1.7.1.txt
process.env.MCPTOOLSHOP_LAUNCH_CONFIG = JSON.stringify({
  toolName: "xrpl-lab",
  owner: "mcp-tool-shop-org",
  repo: "xrpl-lab",
  version: "1.7.1",
  tag: "v1.7.1",
});

require("@mcptoolshop/npm-launcher/bin/mcptoolshop-launch.js");
