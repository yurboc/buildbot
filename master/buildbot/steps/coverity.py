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

from buildbot.process.buildstep import BuildStep
from buildbot.process.buildstep import FAILURE
from buildbot.process.buildstep import SKIPPED
from buildbot.process.buildstep import SUCCESS
from buildbot.process.properties import Interpolate
from buildbot.steps.master import SetProperty
from buildbot.steps.shell import Compile
from buildbot.steps.shell import ShellCommand
from buildbot.steps.slave import SetPropertiesFromEnv
from buildbot.steps.transfer import FileDownload
from buildbot.steps.transfer import FileUpload

""" Build factory example:
ubuntu_coverity = BuildFactory()
ubuntu_coverity.addStep(... download sources ...)
ubuntu_coverity.addStep(... clean build directory ...)
ubuntu_coverity.addStep(CoverityPrepareEnv())
ubuntu_coverity.addStep(CoverityPrepareIni())
ubuntu_coverity.addStep(CoverityConfigProjectId(... project id...))
ubuntu_coverity.addStep(CoverityConfigProjectName(... project name...))
ubuntu_coverity.addStep(CoverityConfigStream('testproject'))
ubuntu_coverity.addStep(CoverityCompile(['scons', '-j16', '--build-release']))
ubuntu_coverity.addStep(CoverityAnalyse())
ubuntu_coverity.addStep(CoverityReport())
ubuntu_coverity.addStep(CoveritySummaryUpload())
ubuntu_coverity.addStep(CoveritySummaryAnalyse(coverity_url='http://some-coverity-server.example.com:8080/'))
"""

""" Dependencies:
1) On master:
- file '~/configs/pst_config.ini' with Coverity configuration.
2) On slave:
- folder '~/buildbot/cov-analysis-linux64-7.5.1' with coverity binaries
- folder '~/buildbot/clientPST' with scripts
- file '~/buildbot/clientPST/PST_AnalysisCommit_xxxxxx.sh' with modifications:
  first argument has ProjectID (PID=$1)
  second argument has Stream Name (STREAM=$2)
- file '~/buildbot/clientPST/PST_ReportCreate_xxxxxx.sh' with modifications:
  first argument has ProjectID (PID=$1)
  second argument has Stream Name (STREAM=$2)
"""


def CoverityPrepareEnv():
    return SetPropertiesFromEnv(
        variables=[
            'CLIENT_PST_PATH',
            'CLIENT_ANAL_BIN',
            'CLIENT_RPRT_BIN',
            ])


def CoverityPrepareIni():
    return FileDownload(
        mastersrc='~/configs/pst_config.ini',
        slavedest='pst_config.ini')


def CoverityConfigProjectId(project_id):
    return SetProperty(
        property="ProjectId",
        value=project_id)


def CoverityConfigProjectName(project_name):
    return SetProperty(
        property="ProjectName",
        value=project_name)


def CoverityConfigStream(default_stream):
    return SetProperty(
        property="StreamName",
        value=Interpolate("%(prop:event.change.number:-{})s".format(default_stream)))


def CoverityCompile(compile_command):
    command = ['cov-build', '--dir', 'build/coverity']
    command.extend(compile_command)
    return Compile(
        command=command,
        description='building cov',
        descriptionDone='cov-build')


def CoverityAnalyse():
    return ShellCommand(
        command=[
            'sh',
            Interpolate('%(prop:CLIENT_PST_PATH)s/%(prop:CLIENT_ANAL_BIN)s'),
            Interpolate('%(prop:ProjectId)s'),
            Interpolate('%(prop:StreamName)s'),
            ],
        description='analysing cov',
        descriptionDone='cov-analyse')


def CoverityReport():
    return ShellCommand(
        command=[
            'sh',
            Interpolate('%(prop:CLIENT_PST_PATH)s/%(prop:CLIENT_RPRT_BIN)s'),
            Interpolate('%(prop:ProjectId)s'),
            Interpolate('%(prop:StreamName)s'),
            ],
        description='report cov',
        descriptionDone='cov-report')


def CoveritySummaryUpload():
    return FileUpload(
        slavesrc=Interpolate('%(prop:ProjectName)s_%(prop:StreamName)s_report.html'),
        masterdest=Interpolate('/tmp/coverity/%(prop:buildername)s/%(prop:buildnumber)s.html'))


class _CoveritySummaryAnalyse(BuildStep):
    name = 'analyse'
    flunkOnFailure = 1

    def __init__(self, coverity_url):
        self.coverity_url = coverity_url
        super(_CoveritySummaryAnalyse, self).__init__()

    def start(self):
        self.addURL('Coverity Connect', self.coverity_url)
        buildername = self.getProperty("buildername")
        buildnumber = self.getProperty("buildnumber")
        with open('/tmp/coverity/%s/%s.html' % (buildername, buildnumber), 'r') as report_file:
            loglines = report_file.readlines()

            iStr = 0
            tokenDefects = -1
            tokenResults = -1

            for line in loglines:
                iStr += 1
                if '<b>Remaining Defect(s)</b>' in line:
                    tokenDefects = iStr
                if '<b>Defect Verification Result</b>' in line:
                    tokenResults = iStr

            if tokenDefects == -1 or tokenResults == -1:
                return self.finished(SKIPPED)

            defectsStr = loglines[tokenDefects + 2]
            resultStr = loglines[tokenResults + 1]

            defectsCountStr = defectsStr[(defectsStr.rfind('&nbsp;') + 6):(defectsStr.rfind('</font>'))]
            covResultStr = resultStr[(resultStr.rfind('">') + 2):(resultStr.rfind('</font>'))]

            self.addHTMLLog('Result "{}": {} defect(s)'.format(covResultStr, defectsCountStr), ''.join(loglines))
            if (int(defectsCountStr) > 0):
                return self.finished(FAILURE)
            return self.finished(SUCCESS)


def CoveritySummaryAnalyse(coverity_url):
    return _CoveritySummaryAnalyse(coverity_url)
