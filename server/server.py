import functools
import json
import os
import socket
import struct
import sys
import threading

import tornado.httpserver
import tornado.ioloop
import tornado.web

class handler(tornado.web.RequestHandler):
  """Add some useful functionality common to all handlers."""
  def accept(self, *mime_types):
    for mime_type in mime_types:
      for element in self.request.headers["accept"].split(","):
        if mime_type == element.split(";")[0]:
          return mime_type

class artcast_handler(handler):
  """Handles each request for an artcast."""
  callbacks = set()
  @staticmethod
  def message(key, data):
    """Called whenever a new artcast value has been received."""
    for callback in artcast_handler.callbacks.copy():
      callback(key, data)

  @tornado.web.asynchronous
  def get(self, key):
    """Called when a client requests an artcast."""
    if self.accept("application/json", "text/html") == "text/html":
      self.render("artcast.html", key=key)
      return

    self.key = key
    artcast_handler.callbacks.add(self.get_result)

  def get_result(self, key, data):
    """Called when a new artcast value has been received."""
    if self.key != key:
      return
    artcast_handler.callbacks.remove(self.get_result)
    self.set_header("Content-Type", "application/json")
    self.write(json.dumps(data))
    self.finish()

def udp_source(group, port, verbose):
  """Listens for new artcast values."""
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
  sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
  sock.bind(("", port))
  mreq = struct.pack("4sl", socket.inet_aton(group), socket.INADDR_ANY)
  sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
  while True:
    key, data = json.loads(sock.recv(4096))
    if options.verbose:
      sys.stderr.write("recv %s : %s\n" % (key, data))
    tornado.ioloop.IOLoop.instance().add_callback(functools.partial(artcast_handler.message, key, data))

if __name__ == "__main__":
  import optparse
  parser = optparse.OptionParser()
  parser.add_option("--client-port", type="int", default=8888, help="Client request input port.  Default: %default")
  parser.add_option("--source-group", default="224.1.1.1", help="Multicast group for receiving source messages.  Default: %default")
  parser.add_option("--source-port", type="int", default=5007, help="Multicast port for receiving source messages.  Default: %default")
  parser.add_option("--uid", type="int", default=None, help="Drop privileges to uid.  Default: %default")
  parser.add_option("--verbose", default=False, action="store_true",  help="Enable debugging output.")
  options, arguments = parser.parse_args()

  if options.verbose:
    for key in sorted(options.__dict__.keys()):
      sys.stderr.write("%s : %s\n" % (key, options.__dict__[key]))

  udp_thread = threading.Thread(target=udp_source, kwargs={"group" : options.source_group, "port" : options.source_port, "verbose" : options.verbose})
  udp_thread.daemon = True
  udp_thread.start()

  application = tornado.web.Application(
    [
    (r"/artcasts/(.*)", artcast_handler)
    ],
    debug = True,
    static_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "content"),
    static_url_prefix = "/content/"
    )

  server = tornado.httpserver.HTTPServer(application)
  server.bind(options.client_port)
  if options.uid is not None:
    os.setuid(options.uid)
  server.start(1)
  tornado.ioloop.IOLoop.instance().start()

