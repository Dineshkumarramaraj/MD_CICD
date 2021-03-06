#!/usr/bin/env python
import argparse
import configparser
import logging
import os
import re
import typing

import yaml


class CLIArgs:
    ADD = 'add'
    REMOVE = 'remove'
    UPDATE = 'update'
    VALIDATE = 'validate'

    def __init__(self):
        """
        CLI Arg Parser: Constructor
        """

        self.parser = argparse.ArgumentParser()

        # Global required options
        self.parser.add_argument("source_file", help="Name of file to read. ", type=str)

        # Global Optional Options
        self.parser.add_argument("-o", "--outfile", help="Name of file to write output. "
                                                         "DEFAULT: Overwrite the source file.",
                                 default=None, type=str)
        self.parser.add_argument("-l", "--list", help="List environments defined in the ini file.",
                                 action='store_true')
        self.parser.add_argument("-d", "--debug", help="Enable debug logging.",
                                 action='store_true')

        # Add subparsers (options for specific operations)
        sub_parser = self.parser.add_subparsers(dest='file_action', help="INI File Operations.")
        for action in [self.ADD, self.UPDATE, self.REMOVE]:
            self._add_options(verb=action, sub_parser=sub_parser)
        self.add_validate(sub_parser=sub_parser)

        # Read the args
        self.args = self.parser.parse_args()

    def _add_options(self, verb: str, sub_parser: typing.Any) -> None:
        """
        Generalized routine to add options to a provided argparse.ArgumentParser.subparser.

        :param verb: Subparser purpose (add, remove, update)
        :param sub_parser: instantiated subparser (see argparse.ArgumentParser.add_subparsers())

        :return: None
        """
        parser = sub_parser.add_parser(verb, help=f"{verb.lower().capitalize()} an entry to file.")
        parser.add_argument('env', help=f"The name of environment to {verb.lower()}.")
        if verb == self.UPDATE:
            parser.add_argument('values', nargs='+', help=f"The 'key:value' pairs of the options to {verb.lower()}.")
        elif verb == self.ADD:
            parser.add_argument('version_str', help='Version text string. 20.1 => TwentyOne')
            parser.add_argument('primary_port', help='Primary Server Port')

    def add_validate(self, sub_parser: typing.Any) -> None:
        """
        Defines the 'validate' arg sub-option.
        :param sub_parser: instantiated subparser (see argparse.ArgumentParser.add_subparsers())

        :return: None
        """
        verb = self.VALIDATE
        sub_parser.add_parser(verb, help=f"{verb.lower().capitalize()} INI file format.")


class IniFile:
    def __init__(self, filespec: str, outfile: typing.Optional[str] = None) -> None:
        """
        Basic Ini File Constructor

        :param filespec: Filespec (path and name) of INI file to read.
        :param outfile: Name of file to write config. (If none, original filespec will be overwritten)

        """
        self.file = filespec
        self.outfile = outfile or self.file
        self.log = logging.getLogger(self.__class__.__name__)
        self.config = self.read_file()
        self.log.debug(f"IniFile '{self.__class__.__name__}' has been instantiated.")

    def read_file(self) -> configparser.ConfigParser:
        """
        Read and parse the Ini File.

        :return: configParser with file contents (or empty if file did not exist/was not found)

        """
        config = configparser.ConfigParser()
        if os.path.exists(self.file):
            config.read(self.file)
            self.log.debug(f"Parsed '{os.path.abspath(self.file)}' successfully.")
        else:
            self.log.error(f"Specified log file ('{self.file}') was not found.")
        return config


class TargetIniFile(IniFile):

    CORE = 'Core'
    TARGETS = 'TARGETS'
    TEMPLATE_SECTION = 'dev_trunk'
    TARGET_TEMPLATE = 'target_ini_section_template.yaml'
    ROOT = 'env_name'
    INSERT_BUILD = '__build__'
    INSERT_BUILD_LOWER = '__build_lower__'
    STATUS_SERVER_PORT = 'STATUS_SERVER_PORT'
    MONITOR_SERVER_PORT = 'MONITOR_SERVER_PORT'

    def _define_new_environment(self, version_string: str):
        with open(self.TARGET_TEMPLATE, "r") as TEMPLATE:
            template_struct = yaml.load(TEMPLATE, Loader=yaml.SafeLoader)

        template = template_struct[self.ROOT]
        for key, data_value in template.items():
            if self.INSERT_BUILD.lower() in str(data_value).lower():
                template[key] = re.sub(rf'{self.INSERT_BUILD}', version_string, data_value)
            elif self.INSERT_BUILD_LOWER.lower() in str(data_value).lower():
                template[key] = re.sub(rf'{self.INSERT_BUILD}', version_string.lower(), data_value)
        return template

    def verify_targets_are_defined(self) -> bool:
        """
        Perform a quick sanity check on the file to verify all relevant sections are defined and registered.

        :return: (bool) - True: all checks passed, False: discrepancies found.

        """
        self.log.debug(f'Verifying that target ini file has {self.CORE} section.')
        if self.CORE not in self.config.sections():
            self.log.error(f"'{self.CORE}' was not found as a section with the ini file.")
            return False

        self.log.debug(f'Verifying that target ini file {self.CORE} section has {self.TARGETS} option.')
        if not self.config.has_option(self.CORE, self.TARGETS):
            self.log.error(f"'{self.TARGETS}' was not found as an option with the '{self.CORE}' section.")
            return False

        # Get list of all registered sections in CORE:TARGETS, and a list of sections in the INI file.
        core_targets = set(self.config.get(self.CORE, self.TARGETS).split(','))
        targets_sections = set(self.get_target_sections())
        sections_match = core_targets == targets_sections
        self.log.debug(f"[{self.CORE}][{self.TARGETS}] and defined sections match 1:1? {sections_match}")

        # Record any mismatches
        if not sections_match:
            undefined_sections = core_targets - targets_sections
            unregistered_sections = targets_sections - core_targets
            if undefined_sections:
                self.log.error(f"The following sections are registered in {self.CORE} but are not defined "
                               f"as sections: {', '.join(undefined_sections)}.")
            if unregistered_sections:
                self.log.error(f"The following sections are defined but are not registered in {self.CORE}: "
                               f"{', '.join(unregistered_sections)}.")

        return sections_match

    def remove_section(self, section_name: str) -> bool:
        """
        Remove a section from the INI file

        :param section_name: Name of the section

        :return: Bool: Successfully removed or not
        """
        sections = self.get_target_sections()
        if section_name not in sections:
            msg = f"Requested section to be removed: '{section_name}' was not found in the defined sections."
            self.log.warning(msg)
            self.log.debug(f"Defined sections: {sections}")
            self.log.info(f"Environment '{section_name}' has NOT been removed.")
            print(msg)
            return False

        self.config.remove_section(section_name)

        result = section_name not in self.get_target_sections()
        if result:
            self.log.info(f"Validation: Environment '{section_name}' has been removed.")
        else:
            self.log.error(f"Validation: Environment '{section_name}' has NOT been removed.")
            print(f"Environment '{section_name}' has NOT been removed.")

        return result

    def update_section(self, section_name: str, option: str, value: typing.Any) -> bool:
        """
        Update a section to the ini file.

        :param section_name: Name of the section/environment to add
        :param option: Keyword to add
        :param value: Value to associate with the keyword/option

        :return: Bool: Value successfully set (True) or not set (False)
        """
        self.log.info(f"Update ENV '{section_name}': Updating '{option}' to '{value}'")
        self.config.set(section=section_name, option=option.lower(), value=value)
        self.log.debug(f"Value check: ENV: {section_name} Option: '{option.lower()}' --> "
                       f"Value: '{self.config.get(section=section_name, option=option)}'")
        return self.config.get(section=section_name, option=option.lower()) == value

    def add_section(self, version_str_text: str, environment: str, primary_port) -> bool:
        """
        Add a section to the file, using the predefined template.
        :param version_str_text: Version string: 20.3 => TwentyThree
        :param environment: Name of environment (dev/qa)
        :param primary_port: Primary port (wil be used to determine internal ports)

        :return: Boolean if section was added to the file. True = Yes, False = No

        """
        section_name = f"{version_str_text.lower()}_{environment.lower()}"
        self.config[section_name] = self._define_new_environment(version_string=version_str_text)
        self.config.set(section_name, self.MONITOR_SERVER_PORT, str(int(primary_port) + 2))
        self.config.set(section_name, self.STATUS_SERVER_PORT, str(int(primary_port) + 3))
        self.log.info(f"Add ENV '{section_name}': using primary port as basis: {primary_port}")
        return self.config.has_section(section_name)

    def get_target_sections(self, sort: bool = False) -> typing.List[str]:
        """
        Get all defined sections that are not the CORE section.

        :param sort: (bool) sort the environment names.

        :return: List of relevant sections.

        """
        sections = [section for section in self.config.sections() if section != self.CORE]
        if sort:
            sections = self._sort_version(sections)
        return sections

    def verify_all_sections_are_fully_defined(self) -> bool:
        """
        Compared all sections to a template section verify all options are correctly specified. If the
        missing section ends in a number, it is not considered missing, since some options can have multiple:
           price_folder <-- If this is missing, this is considered an error
           price_folder2 <--- If this is missing, that may be ok.

        :return: (bool) - True: All sections are correctly specified. False: Some sections are missing sections.

        """

        # Pattern to check if the name ends with a number: x > 1
        ends_with_number = re.compile(r'\w[2-9]+|\w\d{2,}$')

        overall_match = None
        expected_options = set(self.config.options(self.TEMPLATE_SECTION))
        self.log.debug(f'Check ini file sections are fully defined, using {self.TEMPLATE_SECTION} as the template.')
        for section in self.get_target_sections():
            options = set(self.config.options(section))
            all_options_match = options == expected_options

            if not all_options_match:
                template_has_more = [section for section in expected_options - options if
                                     ends_with_number.search(section) is None]
                target_has_more = [section for section in options - expected_options if
                                   ends_with_number.search(section) is None]

                if template_has_more:
                    self.log.error(f"Section '{section}' has missing options: {', '.join(template_has_more)}")
                if target_has_more:
                    self.log.error(f"Section '{section}' has unexpected options: {', '.join(target_has_more)}")

            overall_match = all_options_match if overall_match is None else overall_match and all_options_match

        self.log.info(f"All sections in the {self.file} file are fully defined: {overall_match}")
        return overall_match

    def write_file(self, filename: typing.Optional[str] = None) -> None:
        """
        Writes the file with the Core section first, and then in a custom order (TargetIniFile._sort_version)

        :param filename: (Optional) - Output file, if not specified, overwrite source file.

        :return: None

        """
        filename = filename or self.outfile

        # Determine proper section order
        reordered_sections = self._sort_version(self.config.sections())

        # Update config using sorted section order
        self.config._sections = dict([(section, self.config._sections[section]) for section in reordered_sections])

        # The complexity of the code below (updating internal dictionaries is due to configparser storing all options
        # as lowercase, but the original file is uppercase, so additional logic is required to update the options
        # to uppercase.
        # https://docs.python.org/3/library/configparser.html#customizing-parser-behaviour

        # Sort each section's options alphabetically, and uppercase all option keywords
        # ConfigParser does not maintain the case, so this restores it.
        self.log.debug("Updating all section names to be uppercase.")
        for section in self.config._sections:
            self.config._sections[section] = dict([(name.upper(), value) for name, value in
                                                   sorted(self.config._sections[section].items(), key=lambda t: t[0])])

        # Update the CORE:TARGET string with the sections in the same order as stored in the file.
        self.log.debug(f"Updating '{self.CORE}:{self.TARGETS}' to list all defined environments.")
        new_target_str = ", ".join(reordered_sections[1:])
        self.config.set(self.CORE, self.TARGETS, new_target_str)
        self.config._sections[self.CORE] = dict([(name.upper(), value) for name, value in
                                                 self.config._sections[self.CORE].items()])

        # Write the file
        with open(filename, "w") as INI:
            self.config.write(INI)
        msg = f"Wrote output to {os.path.abspath(filename)}."
        self.log.info(msg)
        print(msg)

    def _sort_version(self, version_list: typing.List[str]) -> typing.List[str]:
        """
        Defined custom sort order used for writing the ini file.
        The first entry is CORE
        All subsequent elements are sorted by the following criteria:
           if the target has a <env>_<version> tag, sort by version
           else if the target has a <env>_<name> tag, sort by env
           else if the target has a <name> tag, sort by name

           This sorts by version (qe and dev are kept together per version), then sort all non-version tags.

        :param version_list: List of ini file sections

        :return: list of sorted ini file sections
        """
        order = {}
        reordered = [self.CORE]
        for version in version_list:

            # Skip this, it will be set as the first element.
            if version == self.CORE:
                continue

            parts = version.split('_')

            # If there was no "_" to split on..
            if len(parts) == 1:
                order[version.lower()] = version

            # If there was a "_", if the second part element of the split has letters,
            # the version will be the first part of the split.
            elif parts[1].isalpha():
                order[f"{parts[0].lower()}-{parts[1]}"] = version

            # Otherwise, the version will be the second part of the split,
            # and the domain will be the first part of the split.
            else:
                order[f"{parts[1]}-{parts[0].lower()}"] = version

        # Sort by dictionary key name
        reordered.extend([version for key, version in sorted(order.items(), key=lambda v: v[0])])
        return reordered


if __name__ == '__main__':
    border = "=" * 120
    cli = CLIArgs()

    # Set up logging
    log_file = f"{'.'.join(cli.args.source_file.split('.')[:-1])}.log"
    log_level = logging.DEBUG if cli.args.debug else logging.INFO
    logging.basicConfig(filename=log_file, level=log_level,
                        format='[%(asctime)s.%(msecs)03d]:[%(levelname)-7s]:[%(name)s.%(funcName)s]: %(message)s',
                        datefmt="%m/%d/%YT%H:%M:%S")
    log = logging.getLogger()
    log.info(border)
    log.info("Execution starting...")

    log.debug(f"CLI Args: {cli.args}")

    # Parse the target INI file
    target = TargetIniFile(filespec=cli.args.source_file, outfile=cli.args.outfile)

    # Based on the global options selected...
    if cli.args.list:
        # NOTE: Do no print the zeroth (first) element [Core] because it is not an environment.
        print(target.get_target_sections(sort=True)[1:])
        exit()

    # Based on the sub-parser selected...
    if cli.args.file_action == cli.REMOVE:
        log.info(f"Removing environment: '{cli.args.env}'")
        target.remove_section(cli.args.env)
        target.write_file()

    elif cli.args.file_action == cli.UPDATE:
        log.info(f"Updating {cli.args.env}: {cli.args.values}")
        for kv_pair in cli.args.values:
            option, value = kv_pair.split(':')
            target.update_section(section_name=cli.args.env, option=option.lower(), value=value)
        target.write_file()

    elif cli.args.file_action == cli.ADD:
        env_name = f"{cli.args.version_str.lower()}_{cli.args.env.lower()}"
        log.info(f"Adding {env_name}: {cli.args.primary_port}")
        target.add_section(version_str_text=cli.args.version_str, primary_port=cli.args.primary_port,
                           environment=cli.args.env)
        env_was_added =env_name in target.get_target_sections()
        log.debug(f"Section {env_name} was added? {env_was_added}")
        if not env_was_added:
            log.error(f"Section {env_name} was NOT added.")
        target.write_file()

    elif cli.args.file_action == cli.VALIDATE:
        log.info(f"Validating {os.path.abspath(cli.args.source_file)}")
        msgs = [f"All targets defined: {target.verify_targets_are_defined()}",
                f"All targets are fully defined: {target.verify_all_sections_are_fully_defined()}"]

        for msg in msgs:
            log.info(msg)
            print(msg)

    log.info("Execution complete.")
    log.info(border)
