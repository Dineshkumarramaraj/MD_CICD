#!/bin/bash
svn export --force svn://pcldevsvn02.development.pclender.local/CFGMGT/Dev/Unit/Kohana $WORKSPACE
echo "Copied config files into Workspace."

svn export --force svn://pcldevsvn02.development.pclender.local/PCLWEBMisc/price_test_files/pclws $WORKSPACE/pclender/
echo "Copied price test files into Workspace."

pnpm install
grunt production

echo "Compilation is done"
echo "Preparing for Fortify Scan"
rm -rf .svn
echo "Removed SVN Folder"
rm -rf node_modules
echo "Removed Node modules"
