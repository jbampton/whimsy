#!/usr/bin/env ruby
PAGETITLE = "Nominate someone for the Board" # Wvisible:meeting
$LOAD_PATH.unshift '/srv/whimsy/lib'
require 'time'
require 'wunderbar'
require 'wunderbar/bootstrap'
require 'whimsy/asf'
require 'whimsy/asf/forms'
require 'whimsy/asf/member-files' # See for nomination file parsing
require 'whimsy/asf/wunderbar_updates'
require 'whimsy/asf/meeting-util'
require 'whimsy/asf/time-utils'
require 'mail'

MAILING_LIST = 'members@apache.org'

def emit_form(title, prev_data)
  _whimsy_panel(title, style: 'panel-success') do
    _form.form_horizontal method: 'post' do
      field = 'availid'

      # Construct list of active voting Members
      ldap_members = ASF.members
      ASF::Person.preload('id', ldap_members)
      members_txt = ASF::Member.list
      already = ASF::MemberFiles.board_nominees
      field_list = {}

      # Fillup dropdown with all active members
      ldap_members.sort_by(&:public_name).each do |nominee|
        next unless members_txt[nominee.id]       # Non-members
        next if members_txt[nominee.id]['status'] # Emeritus/Deceased
        next if already.include? nominee.id       # Previously nominated
        field_list["#{nominee.id}"] = "#{nominee.public_name}"
      end
      _whimsy_forms_select(
        label: 'Select Nominee', 
        name: field,
        multiple: false, 
        values: prev_data[field],
        options: field_list,
        helptext: 'Select the name of a Member to nominate for the Board election'
      )
      _whimsy_forms_input(
        label: 'Nominated by', name: 'nomby', readonly: true, value: $USER
      )
      _whimsy_forms_input(
        label: 'Seconded by', name: 'secby', helptext: 'Optional comma-separated list of seconds availids; ONLY if you have confirmed with the seconds directly'
      )
      field = 'statement'
      _whimsy_forms_input(label: 'Nomination Statement', name: field, rows: 10,
        value: prev_data[field], helptext: 'Explain why you believe this person would be a good Director'
      )
      _whimsy_forms_submitwrap(
        noicon: true, label: 'submit', name: 'submit', value: 'submit', helptext: 'Checkin this nomination and send email to members@'
      )
    end
  end
end

# Validation as needed within the script
# Returns: 'OK' or a text message describing the problem
def validate_form(formdata: {})
  uid = formdata['availid']
  return "You MUST provide a nomination statement for Candidate #{uid}; blank was provided!" if formdata['statement'].empty? 
  chk = ASF::Person[uid]&.asf_member?
  chk.nil? and return "Invalid availid or non-Member nominated; please add manually if desired: (#{uid})\n\nYour Statement:\n#{formdata['statement']}"
  already = ASF::MemberFiles.board_nominees
  return "Candidate #{uid} has already been nominated by #{already[uid]['Nominated by']}" if already.include? uid
  return 'OK'
end

# Handle submission (checkout board_nominations.txt, write form data, checkin file)
# Also creates a board_ballot/availid.txt file for director statements
# @return true if we think it succeeded; false in all other cases
def process_form(formdata: {}, wunderbar: {})
  _h3 "Transcript of updates to nomination files #{ASF::MemberFiles::NOMINATED_BOARD} for candidate #{formdata['availid']}"
  entry = ASF::MemberFiles.make_board_nomination({
    availid: formdata['availid'],
    nomby: formdata['nomby'],
    secby: formdata['secby'],
    statement: formdata['statement']
  })

  environ = Struct.new(:user, :password).new($USER, $PASSWORD)
  ASF::MemberFiles.add_board_ballot(environ, wunderbar, "#{formdata['availid']}", "board_ballot/ += #{formdata['availid']}")
  ASF::MemberFiles.update_board_nominees(environ, wunderbar, [entry], "+= #{formdata['availid']}")
  return true
end

# Send email to members@ with this nomination's data
# Reports status to user in a _div
def send_nomination_mail(formdata: {})
  uid = formdata['availid']
  nomby = formdata['nomby']
  public_name = ASF::Person.new(uid).public_name
  secby = formdata.fetch('secby', nil)
  secby.nil? || secby.empty? ? nomseconds = '' : nomseconds = "Nomination seconded by: #{secby}"
  mail_body = <<-MAILBODY
This nomination for #{public_name} (#{uid}) as a Director
Nominee has been added:

#{formdata['statement']}

#{nomseconds}

--
- #{ASF::Person[nomby].public_name}
  Email generated by Whimsy (#{File.basename(__FILE__)})

MAILBODY
# See check_boardnoms.cgi which parses this in list archives
mailsubject = "[BOARD NOMINATION] #{ASF::Person.new(uid).public_name} (#{uid})"

  ASF::Mail.configure
  mail = Mail.new do
    to MAILING_LIST
    bcc 'notifications@whimsical.apache.org'
    from "#{ASF::Person[nomby].public_name} <#{nomby}@apache.org>"
    subject mailsubject
    text_part do
      body mail_body
    end
  end
  begin
    mail.deliver!
  rescue StandardError => e
    _div.alert.alert_danger role: 'alert' do
      _p.strong "ERROR: email was NOT sent due to: #{e.message} #{e.backtrace[0]}"
      _p do
        _ "To: #{MAILING_LIST}"
        _br
        _ "Subject: #{mailsubject}"
        _br
        _ "#{mail_body}"
      end
    end
    return
  end
  _div.alert.alert_success role: 'alert' do
    _p "The following email was sent:"
    _p do
      _ "To: #{MAILING_LIST}"
      _br
      _ "Subject: #{mailsubject}"
      _br
      _ "#{mail_body}"
    end
  end
  return
end

# Produce HTML
_html do
  _body? do
    # Countdown until nominations for current meeting close
    latest_meeting_dir = ASF::MeetingUtil.latest_meeting_dir
    timelines = ASF::MeetingUtil.get_timeline(latest_meeting_dir)
    t_now = Time.now.to_i
    t_end = Time.parse(timelines['nominations_close_iso']).to_i
    nomclosed = t_now > t_end
    _whimsy_body(
      title: PAGETITLE,
      subtitle: 'About This Script',
      related: {
        'meeting' => 'Member Meeting FAQ and info',
        'check_boardnoms.cgi' => 'Cross-check existing Board nominations',
        'https://www.apache.org/foundation/governance/board' => 'Role of the Board of Directors',
        ASF::SVN.svnpath!('Meetings') => 'Official Meeting Agenda Directory'
      },
      helpblock: -> {
        _b "For: #{timelines['meeting_type']} Meeting on: #{timelines['meeting_iso']}"
        _p do
          _ %Q{
            Use this form to nominate any Member for the ASF Board of Director election.
            It automatically adds a properly formatted nomination to the #{ASF::MemberFiles::NOMINATED_BOARD} file,
            and will then 
          }
          _strong "send an email to the #{MAILING_LIST} list"
          _ ' from you with the nomination, '
          _a 'as is tradition.', href: 'https://lists.apache.org/list?members@apache.org:2023-2:%22BOARD%20NOMINATION%22'
          _ 'This form only supports adding new nominations; to add seconds or comments, please use SVN.'
        end
      }
    ) do
      if nomclosed
        _h1 'Nominations are now closed!'
        _p 'Sorry, no futher nominations will be accepted for ballots at this meeting.'
      else
        _h3 "Nominations close in #{ASFTime.secs2text(t_end - t_now)} at #{Time.at(t_end).utc} for Meeting: #{timelines['meeting_iso']}"
      end

      _div id: 'nomination-form' do
        if _.post?
          unless nomclosed
            submission = _whimsy_params2formdata(params)
            valid = validate_form(formdata: submission)
          end
          if nomclosed
            _div.alert.alert_warning role: 'alert' do
              _p "Nominations have closed"
            end
          elsif valid == 'OK'
            if process_form(formdata: submission, wunderbar: _)
              _div.alert.alert_success role: 'alert' do
                _p "Your nomination was submitted to svn; now sending email to #{MAILING_LIST}."
              end
              mailval = send_nomination_mail(formdata: submission)
              _pre mailval
            else
              _div.alert.alert_danger role: 'alert' do
                _p do
                  _span.strong "ERROR: Form data invalid in process_form(), update was NOT submitted!"
                  _br
                  _ "#{submission}"
                end
              end
            end
          else
            _div.alert.alert_danger role: 'alert' do
              _p do
                _span.strong "ERROR: Form data invalid in validate_form(), update was NOT submitted!"
                _br
                _p valid
              end
            end
          end
        else # if _.post?
          emit_form('Enter your nomination for a Director Nominee', {})
        end
      end
    end
  end
end
