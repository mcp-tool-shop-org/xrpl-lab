#!/usr/bin/env node
"use strict";

// Pure JSON config — npm-launcher derives asset names from convention:
//   binary:    xrpl-lab-2.5.1-linux-x64
//   checksums: checksums-2.5.1.txt
process.env.MCPTOOLSHOP_LAUNCH_CONFIG = JSON.stringify({
  toolName: "xrpl-lab",
  owner: "mcp-tool-shop-org",
  repo: "xrpl-lab",
  version: "2.5.1",
  tag: "v2.5.1",
});

require("@mcptoolshop/npm-launcher/bin/mcptoolshop-launch.js");
