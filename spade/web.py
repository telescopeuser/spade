import logging
import socket

from aiohttp import web as aioweb
import aiohttp_jinja2
import jinja2
from aioxmpp import PresenceType

logger = logging.getLogger("spade.Web")


def unused_port(hostname):
    """Return a port that is unused on the current host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((hostname, 0))
        return s.getsockname()[1]


async def start_server_in_aiothread(handler, hostname, port, agent):
    loop = agent.aiothread.loop
    agent.web.server = await loop.create_server(handler, hostname, port)
    logger.info(f"Serving on http://{hostname}:{port}/")


class WebApp(object):
    def __init__(self, agent):
        self.agent = agent
        self.app = None
        self.handler = None
        self.server = None
        self.hostname = None
        self.port = None

    def start(self, hostname=None, port=None, templates_path=None):
        self.hostname = hostname if hostname else "localhost"
        if port:
            self.port = port
        elif not self.port:
            self.port = unused_port(self.hostname)
        self.app = aioweb.Application()
        internal_loader = jinja2.PackageLoader("spade", package_path='templates', encoding='utf-8')
        if templates_path:
            loader = jinja2.ChoiceLoader([
                jinja2.FileSystemLoader(templates_path),
                internal_loader
            ])
        else:
            loader = internal_loader
        aiohttp_jinja2.setup(self.app, loader=loader, extensions=['jinja2_time.TimeExtension'])
        self.setup_routes()
        self.handler = self.app.make_handler()
        self.agent.submit(start_server_in_aiothread(self.handler, self.hostname, self.port, self.agent))

    def setup_routes(self):
        self.app.router.add_get("/", self.agent_index)
        self.app.router.add_get("/behaviour/{behaviour_type}/{behaviour_class}/", self.get_behaviour)
        self.app.router.add_get("/behaviour/{behaviour_type}/{behaviour_class}/kill/", self.kill_behaviour)

    @aiohttp_jinja2.template('agent.html')
    async def agent_index(self, request):
        contacts = [{"jid": jid,
                     "avatar": self.agent.build_avatar_url(jid.bare()),
                     "available": c["presence"].type_ == PresenceType.AVAILABLE if "presence" in c.keys() else False,
                     "show": str(c["presence"].show).split(".")[1] if "presence" in c.keys() else None,
                     } for jid, c in self.agent.presence.get_contacts().items() if jid.bare() != self.agent.jid.bare()]
        return {
            "agent": self.agent,
            "contacts": contacts
        }

    @aiohttp_jinja2.template('behaviour.html')
    async def get_behaviour(self, request):
        behaviour_str = request.match_info['behaviour_type'] + "/" + request.match_info['behaviour_class']
        behaviour = self.find_behaviour(behaviour_str)
        return {
            "agent": self.agent,
            "behaviour": behaviour,
        }

    async def kill_behaviour(self, request):
        behaviour_str = request.match_info['behaviour_type'] + "/" + request.match_info['behaviour_class']
        behaviour = self.find_behaviour(behaviour_str)
        behaviour.kill()
        raise aioweb.HTTPFound('/')

    def find_behaviour(self, behaviour_str):
        behav = None
        for behaviour in self.agent.behaviours:
            if str(behaviour) == behaviour_str:
                behav = behaviour
                break
        return behav
