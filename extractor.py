from ast import arg
import json
import os
import shutil
import sys
from bashlex import parser, ast
from dockerfile_parse import DockerfileParser

# Usage
# show extracted target pinning
# $ pyton3 extractor.py [target Dockerfile path]

# show only parsed result
# $ python3 extractor.py --only-parse [target Dockerfile path]

DOCKERFILE_FILENAME = "Dockerfile"


def parse_top_level(dockerfile_path):
    path = dockerfile_path
    # dockerfile_parse does not allow file name other than DOCKERFILE_FILENAME
    if not dockerfile_path.endswith(DOCKERFILE_FILENAME):
        tmp = './.tmp'
        if not os.path.exists(tmp):
            os.mkdir(tmp)
        path = os.path.join(tmp, DOCKERFILE_FILENAME)
        shutil.copyfile(dockerfile_path, path)
        dfp = DockerfileParser(path)
        result = dfp.json
        shutil.rmtree(tmp)
        return json.loads(result)
    else:
        dfp = DockerfileParser(path)
        return json.loads(dfp.json)


def parse_bash(top_level_parsed_dockerfile):
    parsed_lines = []
    for line in top_level_parsed_dockerfile:
        inst, argument = list(line.items())[0]
        # If target instruction is a RUN command, parsing is performed
        if inst == "RUN":
            try:
                trees = parser.parse(argument)
                parsed_lines.append({inst: trees})
            except:
                print('error: can not parse\n' + argument)
                continue
        else:
            parsed_lines.append(line)
    return parsed_lines


def parse_dockerfile(dockerfile_path):
    return parse_bash(parse_top_level(dockerfile_path))


def parse_variable(argument):
    variables = {}
    if '=' in argument:
        # eg. ENV abc=hello
        for assign in argument.split(' '):
            if ('=' in assign) == False:
                # Skip ' ' to parse "ENV abc=bye def=abc"
                continue
            variables[assign.split('=')[0].strip()] = assign.split('=')[
                1].strip()
    else:
        # eg. ENV abc hello
        if len(argument.split(' ')) != 2:
            return variables
        variables[argument.split(' ')[0].strip()] = argument.split(' ')[
            1].strip()
    return variables


class nodevisitor(ast.nodevisitor):
    def __init__(self, positions):
        self.positions = positions

    def visitcommand(self, n, parts):
        self.positions.append(parts)
        return False


def replace_variable(parsed_dockerfile):
    # Make a variable table
    variables = {}
    for line in parsed_dockerfile:
        inst, argument = list(line.items())[0]
        if inst == "ENV" or inst == "ARG":
            table = parse_variable(argument)

            # If a variable is used in a variable definition, it is replaced recursively
            while True:
                f = True
                for key in table:
                    for val in variables:
                        if '$' + val in table[key]:
                            if '$' + val in variables[val]:
                                continue
                            table[key] = table[key].replace(
                                '$' + val, variables[val].strip('"'))
                            f = False
                        if '${' + val + '}' in table[key]:
                            if '${' + val + '}' in variables[val]:
                                continue
                            table[key] = table[key].replace(
                                '${' + val + '}', variables[val].strip('"'))
                            f = False
                if f:
                    break

            variables.update(table)

    variables = sorted(variables.items(), key=lambda i: len(i[0]), reverse=True)

    # Replace variables
    for line in parsed_dockerfile:
        inst, argument = list(line.items())[0]
        if inst == "ENV" or inst == "ARG":
            continue

        # Replace variables defined in bash scripts
        bash_variables = {}
        if inst == "RUN":
            assign_nodes = []
            trees = parser.parse(argument)
            for tree in trees:
                visitor = nodevisitor(assign_nodes)
                visitor.visit(tree)
                for assign_node in assign_nodes:
                    for node in assign_node:
                        if node.kind == 'word':
                            if len(node.word.split('=')) == 2:
                                bash_variables[node.word.split('=')[0].strip()] = node.word.split('=')[
                                    1].strip()
                        if node.kind == 'assignment':
                            bash_variables[node.word.split('=')[0].strip()] = node.word.split('=')[
                                1].strip()
        for run_val in bash_variables:
            if '$' + run_val in argument:
                argument = argument.replace(
                    '$' + run_val, bash_variables[run_val])
            if '${' + run_val + '}' in argument:
                argument = argument.replace(
                    '${' + run_val + '}', bash_variables[run_val])

        # Replace variables defined in dockerfile
        for variable in variables:
            key, val = variable
            if '$' + key in argument:
                argument = argument.replace('$' + key, val.strip('"'))
            if '${' + key + '}' in argument:
                argument = argument.replace('${' + key + '}', val.strip('"'))
        line[inst] = argument
    return parsed_dockerfile


def extract_commands(dockerfile):
    commands = []
    for line in dockerfile:
        inst, argument = list(line.items())[0]
        if inst == 'RUN':
            trees = parser.parse(argument)
            cmd_nodes = []
            for tree in trees:
                visitor = nodevisitor(cmd_nodes)
                visitor.visit(tree)

            for cmd_node in cmd_nodes:
                for node in cmd_node:
                    if node.kind == 'word':
                        commands.append(node.word)
                        break
    return commands


def extract_urls(dockerfile):
    urls = []
    for line in dockerfile:
        inst, argument = list(line.items())[0]
        if inst == 'RUN':
            try:
                trees = parser.parse(argument)
            except:
                continue
            url_nodes = []
            for tree in trees:
                visitor = nodevisitor(url_nodes)
                visitor.visit(tree)

            for url_node in url_nodes:
                f = False
                for node in url_node:
                    if node.kind != 'word':
                        continue
                    if node.word == 'curl' or node.word == 'wget':
                        f = True
                    if f and node.word.startswith('http'):
                        urls.append(node.word)
    return urls


def extract_url_based_version_pinning(dockerfile_path):
    top_level_parsed_dockerfile = parse_top_level("./tests/Dockerfile.test")
    replaced_dockerfile = replace_variable(top_level_parsed_dockerfile)
    print_result(extract_urls(replaced_dockerfile))


# If you wanna change output format, please edit this function
def print_result(result_list):
  for l in result_list:
    print(l)


def main():
    if len(sys.argv) == 2:
        extract_url_based_version_pinning("./tests/Dockerfile.test")
    elif len(sys.argv) == 3 and sys.argv[1] == '--only-parse':
        lines = parse_dockerfile("./tests/Dockerfile.test")
        print_result(lines)
    else:
        print('Usage:\npython3 extractor.py [--only-parse] path')


if __name__ == '__main__':
    main()
