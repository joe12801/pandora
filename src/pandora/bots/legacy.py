# -*- coding: utf-8 -*-

import asyncio
import uuid

from rich.prompt import Prompt, Confirm

from .. import __version__
from ..openai.api import ChatGPT
from ..openai.utils import Console


class ChatPrompt:
    def __init__(self, prompt: str = None, parent_id=None, message_id=None):
        self.prompt = prompt
        self.parent_id = parent_id if parent_id else self.gen_message_id()
        self.message_id = message_id if message_id else self.gen_message_id()

    @staticmethod
    def gen_message_id():
        return str(uuid.uuid4())


class State:
    def __init__(self, title=None, conversation_id=None, model_slug=None, user_prompt=ChatPrompt(),
                 chatgpt_prompt=ChatPrompt()):
        self.title = title
        self.conversation_id = conversation_id
        self.model_slug = model_slug
        self.user_prompt = user_prompt
        self.chatgpt_prompt = chatgpt_prompt


class ChatBot:
    def __init__(self, chatgpt: ChatGPT):
        self.chatgpt = chatgpt
        self.state = None

    def run(self):
        conversation_base = self.__choice_conversation()
        if conversation_base:
            self.__load_conversation(conversation_base['id'])
        else:
            self.__new_conversation()

        self.__talk_loop()

    def __talk_loop(self):
        while True:
            Console.info_b('You:')

            prompt = self.__get_input()
            if not prompt:
                continue

            if '/' == prompt[0]:
                self.__process_command(prompt)
                continue

            self.__talk(prompt)

    @staticmethod
    def __get_input():
        lines = []
        while True:
            line = input()

            if not line:
                break
            if '/' == line[0]:
                return line

            lines.append(line)

        return '\n'.join(lines)

    def __process_command(self, command):
        command = command.strip().lower()

        if '/quit' == command or '/exit' == command or '/bye' == command:
            raise KeyboardInterrupt
        elif '/del' == command or '/delete' == command or '/remove' == command:
            self.__del_conversation(self.state)
        elif '/title' == command or '/set_title' == command or '/set-title' == command:
            self.__set_conversation_title(self.state)
        elif '/select' == command:
            self.run()
        elif '/refresh' == command or '/reload' == command:
            self.__load_conversation(self.state.conversation_id)
        elif '/new' == command:
            self.__new_conversation()
            self.__talk_loop()
        elif '/regen' == command or '/regenerate' == command:
            self.__regenerate_reply(self.state)
        elif '/token' == command:
            self.__print_access_token()
        elif '/cls' == command or '/clear' == command:
            self.__clear_screen()
        elif '/ver' == command or '/version' == command:
            self.__print_version()
        else:
            self.__print_usage()

    @staticmethod
    def __print_usage():
        Console.info_b('\n#### Command list:')
        print('/?\t\tShow this help message.')
        print('/title\t\tSet the current conversation\'s title.')
        print('/select\t\tChoice a different conversation.')
        print('/reload\t\tReload the current conversation.')
        print('/regen\t\tRegenerate response.')
        print('/new\t\tStart a new conversation.')
        print('/del\t\tDelete the current conversation.')
        print('/token\t\tPrint your access token.')
        print('/clear\t\tClear your screen.')
        print('/version\t\tPrint the version of Pandora.')
        print('/exit\t\tExit Pandora.')
        print()

    def __print_access_token(self):
        Console.warn_b('\n#### Your access token (keep it private)')
        Console.warn(self.chatgpt.access_token)
        print()

    def __clear_screen(self):
        Console.clear()

        if self.state:
            self.__print_conversation_title(self.state.title)

    @staticmethod
    def __print_version():
        Console.debug_bh('#### Version: {}'.format(__version__))
        print()

    def __new_conversation(self):
        self.state = State(model_slug=self.__choice_model()['slug'])

        self.state.title = 'New Chat'
        self.__print_conversation_title(self.state.title)

    @staticmethod
    def __print_conversation_title(title: str):
        Console.info_bh('==================== {} ===================='.format(title))
        Console.debug_h('Double enter to send. Type /? for help.')

    def __set_conversation_title(self, state: State):
        if not state.conversation_id:
            Console.error('#### Conversation has not been created.')
            return

        new_title = Prompt.ask('New title')
        if len(new_title) > 64:
            Console.error('#### Title too long.')
            return

        if self.chatgpt.set_conversation_title(state.conversation_id, new_title):
            state.title = new_title
            Console.debug('#### Set title success.')
        else:
            Console.error('#### Set title failed.')

    def __del_conversation(self, state: State):
        if not state.conversation_id:
            Console.error('#### Conversation has not been created.')
            return

        if not Confirm.ask('Are you sure?', default=False):
            return

        if self.chatgpt.del_conversation(state.conversation_id):
            self.run()
        else:
            Console.error('#### Delete conversation failed.')

    def __load_conversation(self, conversation_id):
        if not conversation_id:
            return

        self.state = State(conversation_id=conversation_id)

        nodes = []
        result = self.chatgpt.get_conversation(conversation_id)
        current_node_id = result['current_node']

        while True:
            node = result['mapping'][current_node_id]
            if not node['parent']:
                break

            nodes.insert(0, node)
            current_node_id = node['parent']

        self.state.title = result['title']
        self.__print_conversation_title(self.state.title)

        for node in nodes:
            message = node['message']
            if 'model_slug' in message['metadata']:
                self.state.model_slug = message['metadata']['model_slug']

            role = message['author']['role'] if 'author' in message else message['role']

            if 'user' == role:
                prompt = self.state.user_prompt

                Console.info_b('You:')
                Console.info(message['content']['parts'][0])
            else:
                prompt = self.state.chatgpt_prompt

                Console.success_b('ChatGPT:')
                Console.success(message['content']['parts'][0])

            prompt.prompt = message['content']['parts'][0]
            prompt.parent_id = node['parent']
            prompt.message_id = node['id']

            print()

    def __talk(self, prompt):
        Console.success_b('ChatGPT:')

        first_prompt = not self.state.conversation_id
        self.state.user_prompt = ChatPrompt(prompt, parent_id=self.state.chatgpt_prompt.message_id)

        generator = self.chatgpt.talk(prompt, self.state.model_slug, self.state.user_prompt.message_id,
                                      self.state.user_prompt.parent_id, self.state.conversation_id)
        asyncio.run(self.__print_reply(generator))

        if first_prompt:
            new_title = self.chatgpt.gen_conversation_title(self.state.conversation_id, self.state.model_slug,
                                                            self.state.chatgpt_prompt.message_id)
            self.state.title = new_title
            Console.debug_bh('#### Title generated: ' + new_title)

    def __regenerate_reply(self, state):
        if not state.conversation_id:
            Console.error('#### Conversation has not been created.')
            return

        generator = self.chatgpt.regenerate_reply(state.user_prompt.prompt, state.model_slug, state.conversation_id,
                                                  state.user_prompt.message_id, state.user_prompt.parent_id)
        print()
        Console.success_b('ChatGPT:')
        asyncio.run(self.__print_reply(generator))

    async def __print_reply(self, generator):
        p = 0
        async for result in await generator:
            if result['error']:
                raise Exception(result['error'])

            if not result['message']:
                raise Exception('miss message property.')

            message = result['message']
            text = message['content']['parts'][0][p:]

            p += len(text)

            self.state.conversation_id = result['conversation_id']
            self.state.chatgpt_prompt.prompt = message['content']['parts'][0]
            self.state.chatgpt_prompt.parent_id = self.state.user_prompt.message_id
            self.state.chatgpt_prompt.message_id = message['id']

            if text:
                Console.success(text, end='')

            if message['end_turn']:
                print()
        print()

    def __choice_conversation(self, page=1, page_size=20):
        conversations = self.chatgpt.list_conversations((page - 1) * page_size, page_size)
        if not conversations['total']:
            return None

        choices = ['c']
        items = conversations['items']
        first_page = 0 == conversations['offset']
        last_page = (conversations['offset'] + conversations['limit']) >= conversations['total']

        Console.info_b('Choice conversation (Page {}):'.format(page))
        for idx, item in enumerate(items):
            number = str(idx + 1)
            choices.append(number)
            choices.append('t' + number)
            choices.append('d' + number)
            Console.info('  {}. {}'.format(number, item['title']))

        if not last_page:
            choices.append('n')
            Console.warn('  n. >> Next page')

        if not first_page:
            choices.append('p')
            Console.warn('  p. << Previous page')

        Console.warn('  t?. Set title for the conversation, eg: t1')
        Console.warn('  d?. Delete the conversation, eg: d1')
        Console.warn('  c. ** Start new chat')

        while True:
            choice = Prompt.ask('Your choice', choices=choices, show_choices=False)
            if 'c' == choice:
                return None

            if 'n' == choice:
                return self.__choice_conversation(page + 1, page_size)

            if 'p' == choice:
                return self.__choice_conversation(page - 1, page_size)

            if 't' == choice[0]:
                self.__set_conversation_title(State(conversation_id=items[int(choice[1:]) - 1]['id']))
                return self.__choice_conversation(page, page_size)

            if 'd' == choice[0]:
                self.__del_conversation(State(conversation_id=items[int(choice[1:]) - 1]['id']))
                continue

            return items[int(choice) - 1]

    def __choice_model(self):
        models = self.chatgpt.list_models()

        size = len(models)
        if 1 == size:
            return models[0]

        choices = []
        Console.info_b('Choice model:')
        for idx, item in enumerate(models):
            number = str(idx + 1)
            choices.append(number)
            Console.info('  {}. {} - {}'.format(number, item['title'], item['description']))

        while True:
            choice = Prompt.ask('Your choice', choices=choices, show_choices=False)
            return models[int(choice) - 1]
