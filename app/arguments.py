import argparse
import sys


def translate_error(message):
    replacements = {
        'the following arguments are required:': 'нужны следующие аргументы:',
        'unrecognized arguments:': 'неизвестные аргументы:',
        'not allowed with argument': 'нельзя использовать вместе с аргументом',
        'one of the arguments': 'один из аргументов',
        'is required': 'обязателен',
        'expected at least one argument': 'нужен хотя бы один аргумент',
        'expected one argument': 'нужен один аргумент',
        'expected at most one argument': 'допускается не более одного аргумента',
        'expected %s arguments': 'нужно %s аргументов',
        'invalid int value:': 'неверное целое число:',
        'invalid float value:': 'неверное число:',
        'invalid choice:': 'недопустимое значение:',
        'choose from': 'выберите из',
        'ambiguous option:': 'неоднозначный параметр:',
        'could match': 'подходит к',
        'ignored explicit argument': 'лишнее значение аргумента',
        'argument ': 'аргумент ',
    }
    for original, translated in replacements.items():
        message = message.replace(original, translated)
    return message


class RussianHelpFormatter(argparse.HelpFormatter):
    def _format_usage(self, usage, actions, groups, prefix):
        return super()._format_usage(usage, actions, groups, prefix or 'Использование: ')


class RussianArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        add_help = kwargs.pop('add_help', True)
        kwargs.setdefault('formatter_class', RussianHelpFormatter)
        super().__init__(*args, add_help=False, **kwargs)
        self._positionals.title = 'Позиционные аргументы'
        self._optionals.title = 'Параметры'
        if add_help:
            self.add_argument('-h', '--help', action='help', help='показать справку и выйти')

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, f'Ошибка: {translate_error(message)}\n')
