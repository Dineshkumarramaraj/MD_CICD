#!/bin/bash
svn export --force svn://10.9.20.245/LaravelMisc/a2_env_config_files/dev $WORKSPACE/
echo "Copied config files into Workspace."
/data/BuildManifest.sh
composer install --no-dev
npm install
npm run production

echo "Compilation is done"
echo "Preparing for Fortify Scan"
rm -rf .svn
echo "Removed SVN Folder"
rm -rf node_modules
echo "Removed node modules"
