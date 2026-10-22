#!/usr/bin/env node
"use strict";

// Pure JSON config — npm-launcher derives asset names from convention:
//   binary:    xrpl-lab-2.7.8-linux-x64
//   checksums: checksums-2.7.8.txt
process.env.MCPTOOLSHOP_LAUNCH_CONFIG = JSON.stringify({
  toolName: "xrpl-lab",
  owner: "mcp-tool-shop-org",
  repo: "xrpl-lab",
  version: "2.7.8",
  tag: "v2.7.8",
});

require("@mcptoolshop/npm-launcher/bin/mcptoolshop-launch.js");
