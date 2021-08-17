#!/usr/bin/env python

import os
import sys
import socket
import re
import time
import yaml
# Fast zip compatibility with Python 2 and 3
try:
    from itertools import izip as zip
except ImportError:
    pass

from optparse import OptionParser
import rosgraph
import rostopic
import rospy
import genpy
from marti_common_msgs.msg import NodeInfo, TopicInfo, ParamInfo, ServiceInfo

def _check_master(rosmaster):
    try:
        rosmaster.getPid()
    except socket.error:
        # Stealing rostopics exception type for now
        raise rostopic.ROSTopicIOException("Unable to communicate with master!")

class DocTopicReader:
    def __init__(self, rosmaster):
        self.rosmaster = rosmaster
        self.callback_called = False
        self.last_doc_msg = None
        # Setup a node to read topics with
        _check_master(self.rosmaster)
        rospy.init_node('rosman', anonymous=True)

    def doc_topic_callback(self, doc_msg):
        self.last_doc_msg = doc_msg
        self.callback_called = True

    def read_doc_topic(self, topic, timeout_duration=2.0):
        self.callback_called = False
        doc_sub = rospy.Subscriber(topic, NodeInfo, self.doc_topic_callback) 
        timeout = time.time()+timeout_duration
        while time.time() < timeout and self.callback_called == False and \
                not rospy.is_shutdown():
            rospy.rostime.wallsleep(0.1)
        if not self.callback_called:
            self.last_doc_msg = None
        # Let caller know if reading was successful
        return self.callback_called

    def write_node_documentation(self, output_file=sys.stdout):
        # TODO error out correctly if the last topic wasn't read correctly
        if (self.last_doc_msg is None):
            print('DocTopicReader failed to read documentation topic and cannot write out the node documentation')
            return
        self.write_node_header_documentation(output_file)
        self.write_node_subscriptions_documentation(output_file)
        self.write_node_publishers_documentation(output_file)
        self.write_node_parameters_documentation(output_file)
        self.write_node_services_documentation(output_file)

    def write_node_header_documentation(self, output_file=sys.stdout):
        output_file.write("{name} - ({nodelet_manager})\n{description}\n\n".format(name=self.last_doc_msg.name,
            nodelet_manager=self.last_doc_msg.nodelet_manager,
            description=self.last_doc_msg.description if self.last_doc_msg.description else "TODO: node description"))

    def write_node_subscriptions_documentation(self, output_file=sys.stdout):
        output_file.write("Subscriptions:\n")
        subs = [topic for topic in self.last_doc_msg.topics if topic.advertised == False] 
        for sub in subs:
            output_file.write('  * ')
            self.write_topic_info_docstring(sub, output_file)
        output_file.write('\n')

    def write_topic_info_docstring(self, topic_info_msg, output_file=sys.stdout):
        output_file.write("{name} - ({type}) - {description}\n".format(name=topic_info_msg.name,
            type=topic_info_msg.message_type,
            description=topic_info_msg.description))

    def write_node_publishers_documentation(self, output_file=sys.stdout):
        output_file.write("Publishers:\n")
        pubs = [topic for topic in self.last_doc_msg.topics if topic.advertised == True]
        for pub in pubs:
            output_file.write('  * ')
            self.write_topic_info_docstring(pub, output_file)
        output_file.write('\n')

    def write_node_parameters_documentation(self, output_file=sys.stdout):
        if len(self.last_doc_msg.parameters) > 0:
            output_file.write("Parameters:\n")
            for param in self.last_doc_msg.parameters:
                output_file.write('  * ')
                self.write_param_info_docstring(param, output_file)
            output_file.write('\n')

    def write_node_services_documentation(self, output_file=sys.stdout):
        servs = [service for service in self.last_doc_msg.services if service.server == True]
        if len(servs) > 0:
            output_file.write("Services:\n")
            for serv in self.last_doc_msg.services:
                output_file.write('  * ')
                self.write_service_info_docstring(serv, output_file=sys.stdout)
            output_file.write('\n')

    def write_param_info_docstring(self, param_info_msg, output_file=sys.stdout):
        default_val = ""
        type_str = "unknown_type"
        if (param_info_msg.type == ParamInfo.TYPE_DOUBLE):
            default_val = param_info_msg.default_double
            type_str = "double"
            output_file.write("{name} - ({type}, {default:.6g}) - {description}\n".format(name=param_info_msg.name,
                type=type_str, default=default_val, description=param_info_msg.description))
            return
        elif (param_info_msg.type == ParamInfo.TYPE_STRING):
            default_val = param_info_msg.default_string
            type_str = "string"
            output_file.write("{name} - ({type}, {default}) - {description}\n".format(name=param_info_msg.name,
                type=type_str, default=default_val, description=param_info_msg.description))
            return
        elif (param_info_msg.type == ParamInfo.TYPE_INT):
            default_val = param_info_msg.default_int
            type_str = "int"
            output_file.write("{name} - ({type}, {default:d}) - {description}\n".format(name=param_info_msg.name,
                type=type_str, default=default_val, description=param_info_msg.description))
            return
        elif (param_info_msg.type == ParamInfo.TYPE_FLOAT):
            default_val = param_info_msg.default_float
            type_str = "float"
            output_file.write("{name} - ({type}, {default:.6g}) - {description}\n".format(name=param_info_msg.name,
                type=type_str, default=default_val, description=param_info_msg.description))
            return
        elif (param_info_msg.type == ParamInfo.TYPE_BOOL):
            default_val = "true" if param_info_msg.default_bool else "false"
            type_str = "bool"
            output_file.write("{name} - ({type}, {default}) - {description}\n".format(name=param_info_msg.name,
                type=type_str, default=default_val, description=param_info_msg.description))
            return
        # Unknown type write
        output_file.write("{name} - ({type}, {default}) - {description}\n".format(name=param_info_msg.name,
            type=type_str, default=default_val, description=param_info_msg.description))


    def write_service_info_docstring(self, service_info_msg, output_file=sys.stdout):
        output_file.write("{name} - ({type}) - {description}\n".format(name=service_info_msg.name,
            type=service_info_msg.message_type, description=service_info_msg.description))

## TODO make this a document topic reader class that can cache 
## the document messages it reads and do the reading / file output seperatly 
def read_documentation_topic(rosmaster, topic, yaml=False, output_file=sys.stdout):
    topic_reader = DocTopicReader(rosmaster)
    if topic_reader.read_doc_topic(topic):
        if yaml:
            output_file.write(genpy.message.strify_message(topic_reader.last_doc_msg) + '\n')
        else:
            topic_reader.write_node_documentation(output_file)

def get_documentation_publications(rosmaster):
    """
    Get all the current documentation topics in the system
    """
    # get the master system state
    try:
        ros_sys_state = rosmaster.getSystemState()
    except socket.error:
        print('Could not communicate with ROS master!')
        sys.exit(2)
    pubs, _, _ = ros_sys_state
    # doc_matcher = re.compile('/documentation$')
    doc_match_string = '/documentation$'
    doc_topics = []
    doc_node_namespaces = []
    doc_publisher_nodes = []
    for t, n in pubs:
        doc_match = re.search(doc_match_string, t)
        if doc_match:
            # Try stripping the node namespace off the topic
            node_namespace = t[0:doc_match.span()[0]]
            doc_topics.append(t)
            doc_node_namespaces.append(node_namespace)
            doc_publisher_nodes.append(n)
            #print('node {0} with node namespace {1} publishes topic {2}'.format(n, node_namespace ,t))
    return doc_topics, doc_node_namespaces, doc_publisher_nodes

def rosman_node(rosmaster, node_name, yaml=False):
    # The doc_node_namespaces are probably the more accurate "node" information for the documentation topic
    # since the doc_publisher nodes for a doc topic can be a nodelet manager
    documentation_info = get_documentation_publications(rosmaster)
    # TODO I don't think I'm iterating through this correctly
    for topic, node_namespace, publishers in zip(documentation_info[0], documentation_info[1], documentation_info[2]):
        if node_name in node_namespace or node_name in publishers:
            # TODO handle or buble up the handling of file opening/closing if the 
            # output is desired from something other than stdout
            read_documentation_topic(rosmaster, topic, yaml=yaml)

def _rosman_node_main(argv):
    """
    Entry point for rosman node command
    """
    args = argv[2:]
    parser = OptionParser(usage='usage: %prog node node1 [node2...]')
    parser.add_option('-y','--yaml', dest="yaml", action="store_true", 
            default=False, help='print node documentation output as a yaml compliant string')
    (options, args) = parser.parse_args(args)
    
    if not args:
        parser.error('You must specify at least one node name')

    ros_master = rosgraph.Master('/rosman')
    for node in args:
        rosman_node(ros_master, node, yaml=options.yaml)

def _rosman_topics_main(argv):
    """
    Entry point for rosman topics command
    """
    args = argv[2:]
    parser = OptionParser(usage='usage: %prog topics topic1 [topic2...]')
    (options, args) = parser.parse_args(args)

    if not args:
        parser.error('You must specify at least one topic name')
    for node in args:
        print('querying node {n}'.format(n=node))

def _rosman_params_main(argv):
    """
    Entry point for rosman params command
    """
    args = argv[2:]
    parser = OptionParser(usage='usage: %prog params param1 [param2...]')
    (options, args) = parser.parse_args(args)

    if not args:
        parser.error('You must specify at least one param name')
    for node in args:
        print('querying node {n}'.format(n=node))

def _rosman_services_main(argv):
    """
    Entry point for rosman services command
    """
    args = argv[2:]
    parser = OptionParser(usage='usage: %prog services service1 [service2...]')
    (options, args) = parser.parse_args(args)

    if not args:
        parser.error('You must specify at least one service name')
    for node in args:
        print('querying node {n}'.format(n=node))

def _tool_usage(return_error=True):
    """
    Print the full usage information for the rosman tool.
    @param return_error set to true to return from this printout with error code os.EX_USAGE, otherwise exit returning 0.
    """
    print("""rosman is a command-line tool for printing documentation about nodes, topics, and parameters from a live or playback system.

Commands:
\trosman node\tGet overview documentation for a running node
\trosman topics\tGet documentation for a desired topic
\trosman params\tGet documentation for a desired parameter
\trosman services\tGet documentation about a desired service

Type rosman <command> -h for more detailed usage, e.g. 'rosman params -h'
""")
    if return_error:
        sys.exit(getattr(os, 'EX_USAGE', 1))
    else:
        sys.exit(0)

def rosmanmain(argv=None):
    """
    Prints rosman main entrypoint.
    @param argv: override sys.argv
    @param argv: [str]
    """
    if argv == None:
        argv = sys.argv
    if len(argv) == 1:
        _tool_usage()
    try:
        command = argv[1]
        if command == 'node':
            _rosman_node_main(argv)
        elif command == 'topics':
            _rosman_topics_main(argv)
        elif command == 'params':
            _rosman_params_main(argv)
        elif command == 'services':
            _rosman_services_main(argv)
        elif command in ('-h', '--help'):
            _tool_usage(return_error=False)
        else:
            _tool_usage()
    except KeyboardInterrupt:
        pass

