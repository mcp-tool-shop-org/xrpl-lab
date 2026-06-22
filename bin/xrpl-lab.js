#!/usr/bin/env node
"use strict";

// Pure JSON config — npm-launcher derives asset names from convention:
//   binary:    xrpl-lab-2.2.0-linux-x64
//   checksums: checksums-2.2.0.txt
process.env.MCPTOOLSHOP_LAUNCH_CONFIG = JSON.stringify({
  toolName: "xrpl-lab",
  owner: "mcp-tool-shop-org",
  repo: "xrpl-lab",
  version: "2.2.0",
  tag: "v2.2.0",
});

require("@mcptoolshop/npm-launcher/bin/mcptoolshop-launch.js");
