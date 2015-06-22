# Copyright (C) 2015 Yuriy Botsev
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

""" Build factory example:
ubuntu_klocwork = BuildFactory()
ubuntu_klocwork.addStep(KlocworkGetToken())
ubuntu_klocwork.addStep(KlocworkInject(['scons', '-j16', '--build-release']))
ubuntu_klocwork.addStep(KlocworkCheckLicense('27000@192.168.1.1'))
ubuntu_klocwork.addStep(KlocworkBuild('http://127.0.0.1:8080/MYPROJECT'))
ubuntu_klocwork.addStep(KlocworkUpload('http://127.0.0.1:8080/', 'MYPROJECT'))
ubuntu_klocwork.addStep(KlocworkAnalyseReport(
    project_name = 'MYPROJECT', klocwork_url = 'http://127.0.0.1:8080', klocwork_user = 'tester',
    token_host = 'builder-klocwork', token_port = '8080', token_user = 'Tester Name'))
"""

""" Dependencies:
On slave:
- configured Klocwork; permissions for builder
- created project in the Klocwork web interface
- folder '~/buildbot/klocwork/kw-server' with klocwork server binaries
- folder '~/buildbot/klocwork/kw-user' with klocwork client binaries
"""

import json
import os
import urllib
import urllib2

from buildbot.process.buildstep import BuildStep
from buildbot.process.buildstep import FAILURE
from buildbot.process.buildstep import SUCCESS
from buildbot.steps.shell import ShellCommand
from buildbot.steps.transfer import FileUpload


def KlocworkGetToken():
    return FileUpload(
        slavesrc='~/.klocwork/ltoken',
        masterdest='/tmp/klocwork/ltoken')


def KlocworkInject(cmd):
    command = ['kwinject', '--output', 'project_kwinject.out']
    command.extend(cmd)
    return ShellCommand(
        command=command,
        haltOnFailure=1,
        description='injecting',
        descriptionDone='inject'
    )


def KlocworkCheckLicense(license_server):
    return ShellCommand(
        command=[
            'lmstat', '-a', '-c', license_server, '-f', 'kwbuildproject'],
        haltOnFailure=1,
        warnOnFailure=1,
        description='checking license',
        descriptionDone='check license')


def KlocworkBuild(url):
    return ShellCommand(
        command=[
            'kwbuildproject', '--incremental',
            '--url', url, 'project_kwinject.out',
            '--tables-directory', 'project_tables'],
        haltOnFailure=1,
        logfiles=dict(debug='project_tables/build.log'),
        description='building',
        descriptionDone='build')


def KlocworkUpload(url, project):
    return ShellCommand(
        command=[
            'kwadmin',
            '--url', url,
            'load', project, 'project_tables'],
        haltOnFailure=1,
        description='uploading',
        descriptionDone='upload')


class _Key(object):

    def __init__(self, attrs):
        self.id = attrs["id"]
        self.name = attrs["name"]

    def __str__(self):
        return self.name


class _Report(object):

    def __init__(self, attrs):
        self.rows = attrs["rows"]
        self.columns = attrs["columns"]
        self.data = attrs["data"]

    def __str__(self):
        result = ""
        for x in range(len(self.rows)):
            for y in range(len(self.columns)):
                result += '{} ({}): {} issue(s)\n'.format(str(self.rows[x]), str(self.columns[y]), str(self.data[x][y]))
        return result

    def countIssues(self):
        count = 0
        for x in range(len(self.rows)):
            for y in range(len(self.columns)):
                count += self.data[x][y]
        return count


class KlocworkAnalyseReport(BuildStep):
    name = 'analyse'
    flunkOnFailure = 1

    def __init__(self, project_name, klocwork_url, klocwork_user,
                 token_host, token_port, token_user, **buildstep_kwargs):
        BuildStep.__init__(self, **buildstep_kwargs)
        self.project_name = project_name
        self.klocwork_url = klocwork_url
        self.klocwork_user = klocwork_user
        self.token_host = token_host
        self.token_port = token_port
        self.token_user = token_user

    def start(self):
        def getToken(tokenfile, host, port, user):
            ltoken = os.path.normpath(os.path.expanduser(tokenfile))
            ltokenFile = open(ltoken, 'r')
            for r in ltokenFile:
                rd = r.strip().split(';')
                if rd[0] == host and rd[1] == str(port) and rd[2] == user:
                    ltokenFile.close()
                    return rd[3]
            ltokenFile.close()

        def from_json(json_object):
            if 'rows' in json_object:
                return _Report(json_object)
            if 'id' in json_object:
                return _Key(json_object)
            return json_object

        self.addURL('Klocwork Review', 'http://kenny.rnd.samsung.ru:8080/review/')

        url = '{}/review/api'.format(self.klocwork_url)
        values = {
            "project": self.project_name,
            "user": self.klocwork_user,
            "action": "report",
            "filterQuery": "Status:Fix,Analyze",
            "x": "Owner",
            }

        loginToken = getToken('/tmp/klocwork/ltoken',
                              self.token_host,
                              self.token_port,
                              self.token_user)
        if loginToken is not None:
            values["ltoken"] = loginToken

        data = urllib.urlencode(values)
        req = urllib2.Request(url, data)
        response = urllib2.urlopen(req)

        completeLog = ""
        totalIssues = 0
        for record in response:
            report = json.loads(record, object_hook=from_json)
            completeLog += str(report)
            totalIssues += report.countIssues()

        completeLog += '\n==========\n'
        completeLog += 'Total: {} issue(s)\n'.format(totalIssues)
        self.addCompleteLog('{} issue(s)'.format(totalIssues), completeLog)

        if (totalIssues > 0):
            return self.finished(FAILURE)
        return self.finished(SUCCESS)
