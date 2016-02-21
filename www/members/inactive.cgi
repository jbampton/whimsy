#!/usr/bin/ruby1.9.1
$LOAD_PATH.unshift File.realpath(File.expand_path('../../../lib', __FILE__))

require 'whimsy/asf'
require 'wunderbar/bootstrap'
require 'date'
require 'json'
require 'tmpdir'

# locate and read the attendance file
MEETINGS = ASF::SVN['private/foundation/Meetings']
attendance = JSON.parse(IO.read("#{MEETINGS}/attendance.json"))
latest = Dir["#{MEETINGS}/2*"].sort.last.untaint
tracker = JSON.parse(IO.read("#{latest}/non-participants.json"))

# determine user's name as found in members.txt
name = ASF::Member.find_text_by_id($USER).to_s.split("\n").first
matrix = attendance['matrix'][name]

# produce HTML
_html do
  _style :system
  _style %{
    div.status, .status form {margin-left: 16px}
    .btn {margin: 4px}
    form {margin-bottom: 1em}
    .transcript {margin: 0 16px}
    .transcript pre {border: none; line-height: 0}
    pre._hilite {background-color: yellow}
  }

  if not tracker[$USER]
    _p.alert.alert_success "You are not on the list"
  else
    _p.alert.alert_warning "You have missed the last " + 
      tracker[$USER]['missed'].to_s + " meetings."

    if _.post? and @status
      _h3_ 'Session Transcript'

      # setup authentication
      if $PASSWORD
        auth = [['--username', $USER, '--password', $PASSWORD]]
      else
        auth = [[]]
      end

      # apply and commit changes
      Dir.mktmpdir do |dir|
        _div_.transcript do
          work = `svn info #{latest}`[/URL: (.*)/, 1]
          _.system ['svn', 'checkout', auth, '--depth', 'empty', work, dir]
           json = File.join(dir, 'non-participants.json')
          _.system ['svn', 'update', auth, json]
          tracker = JSON.parse(IO.read(json))
          tracker[$USER]['status'] = @status
          IO.write(json, JSON.pretty_generate(tracker))
          _.system ['svn', 'diff', json], hilite: [/"status":/],
            class: {hilight: '_stdout _hilite'}
          _.system ['svn', 'commit', auth, json, '-m', @status]
        end
      end
    end

    _h1_ 'Status'

    _div.status do
      _p %{
        We are reaching out to those members that have not participated in
        ASF Members Meetings or Elections in over five years, and asking each
        of them whether they wish to remain active or go emeritus.  You can
        indicate your choice by pushing one of the buttons below.
      }

      _p_ do
        _span 'Your current status is: '
        _code tracker[$USER]['status']
      end

      _p 'Update your status:'

      _form method: 'post' do
        _button.btn.btn_success 'I wish to remain active',
          name: 'status', value: 'remain active',
          disabled: tracker[$USER]['status'] == 'remain active'
        _button.btn.btn_warning 'I consent to being placed in emeritus status',
          name: 'status', value: 'go emeritus',
          disabled: tracker[$USER]['status'] == 'go emeritus'
      end

      _p_ %{
        Should you chose to remain active, please consider participating, at
        least by proxy, in the upcoming membership meeting.  See the links
        below for more information.
      }
    end

    _h3_ 'Links'

    _ul do
      _li do
        _a 'Meeting Notice', href:
          'https://svn.apache.org/repos/private/foundation/Meetings/' +
          File.basename(latest) + '/NOTICE.txt'
      end
      _li do
        _a 'Meeting Agenda', href:
          'https://svn.apache.org/repos/private/foundation/Meetings/' +
          File.basename(latest) + '/agenda.txt'
      end
      _li do
        _a 'Assign a proxy', href: 'https://whimsy.apache.org/members/proxy'
      end
      _li do
        _a 'Members.txt', href:
          'https://svn.apache.org/repos/private/foundation/members.txt'
      end
    end
  end

  _h1_ 'Attendance history'

  if not name

    _p.alert.alert_danger "#{$USER} not found in members.txt"

  elsif not matrix

    _p.alert.alert_danger "#{name} not found in attendance matrix"

  else

    count = 0
    _table.table.table_sm style: 'margin: 0 24px; width: auto' do
      _thead do
        _tr do
          _th 'Date'
          _th 'Status'
        end
      end

      matrix.sort.reverse.each do |date, status|
        next if status == ' '

        color = 'bg-danger'
        color = 'bg-warning' if %w(e).include? status
        color = 'bg-success' if %w(A V P).include? status

        _tr_ class: color do
          _td do
            _a date, href:
              'https://svn.apache.org/repos/private/foundation/Meetings/' + 
              date
          end

          case status
          when 'A'
            _td 'Attended'
          when 'V'
            _td 'Voted but did not attend'
          when 'P'
            _td 'Attended via proxy'
          when '-'
            _td 'Did not attend'
          when 'e' 
            _td 'Went emeritus'
          else
            _td status
          end
        end
      end
    end
  end
end
