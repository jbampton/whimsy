#
# Overall monitor class is responsible for loading and running each
# monitor in the `monitors` directory, collecting and normalizing the
# results and outputting it as JSON for use in the GUI.
#
# The previous status is passed to the monitor on the next run so it can
# determine when to take non-idempotent actions such as sending a message
#
# The monitors are called frequently, so the return status built up by
# a monitor should be easily comparable with the input status. This means
# using the same key and value formats (at least for monitors that need to
# compare them).
#
# Although both string and symbolic keys can be used in hashes, the syntax
# for symbolic keys is rather neater, so we use symbolic keys throughout.
# This means that the JSON file is parsed into a hash using symbolic keys,
# and any variables used as keys need to be converted to symbols.

require 'json'
require 'time'
require 'thread'

# for debugging purposes must include status
if __FILE__ == $0
  $LOAD_PATH.unshift '/srv/whimsy/lib'
  require 'whimsy/asf/status'
end

class StatusMonitor
  # match http://getbootstrap.com/components/#alerts
  LEVELS = %w(success info warning danger fatal)

  attr_reader :status
  attr_reader :timings # debug timings

  def timediff(what)
    now = Time.now
    @timings << [what, now - @prev]
    @prev = now
  end

  def initialize(args = [])
    @timings = []
    @prev = Time.now
    status_file = File.expand_path('../status.json', __FILE__)
    File.open(status_file, File::RDWR|File::CREAT, 0644, encoding: Encoding::UTF_8) do |file|
      timediff('open')
      # lock the file
      mtime = File.exist?(status_file) ? File.mtime(status_file) : Time.at(0)
      file.flock(File::LOCK_EX)
      timediff('locked')

      # fetch previous status (using symbolic keys)
      begin
        baseline = JSON.parse(file.read, {symbolize_names: true})
      rescue Exception => e
        $stderr.puts "monitor: Failed to read status.json: #{e}"
        baseline = {}
      end
      timediff('parsed')
      baseline[:data] = {} unless baseline[:data].instance_of? Hash

      # If status was updated while waiting for the lock, use the new status
      if not File.exist?(status_file) or mtime != File.mtime(status_file)
        @status = baseline
        return
      end

      timediff('before threads')
      # start each monitor in a separate thread
      threads = []
      self.class.singleton_methods.sort.each do |method|
        next if args.length > 0 and not args.include? method.to_s
        threads << Thread.new do
          begin
            # invoke method to determine current status
            previous = baseline[:data][method.to_sym] || {mtime: Time.at(0)}
            status = StatusMonitor.send(method, previous) || previous

            # convert non-hashes in proper statuses
            if not status.instance_of? Hash
              if status.instance_of? String or status.instance_of? Array
                status = {data: status}
              else
                status = {level: 'danger', data: status.inspect}
              end
            end
          rescue Exception => e
            status = {
              level: 'fatal',
              data: {
                exception: {
                  level: 'fatal',
                  text: e.inspect,
                  data: e.backtrace
                }
              }
            }
          end

          # default mtime to now
          status[:mtime] ||= Time.now if status.instance_of? Hash

          # store status in thread local storage
          Thread.current[:name] = method.to_s
          Thread.current[:status] = status
        end
      end

      timediff('started threads')
      # collect status from each monitor thread
      newstatus = {}
      threads.each do |thread|
        thread.join
        timediff(thread[:name])
        newstatus[thread[:name]] = thread[:status]
      end

      timediff('after threads')
      # normalize status
      status = normalize(data: newstatus)
      status[:mtime] = Time.now.gmtime.iso8601
      @status = status

      timediff('normalized')
      File.write(File.expand_path('../../logs/status.data', __FILE__),
        @status.inspect)

      timediff('status.data')
      # update results
      file.rewind
      file.write JSON.pretty_generate(@status)
      file.flush
      file.truncate(file.pos)
      timediff('status.json')
    end
  end

  ISSUE_TYPE = {
    'success' => 'successes',
    'info'    => 'updates',
    'warning' => 'warnings',
    'danger'  => 'issues'
  }

  ISSUE_TYPE.default = 'problems'

  # default fields, and propagate status 'upwards'
  def normalize(status)
    # convert strings and arrays to status hashes
    if status.instance_of? String or status.instance_of? Array
      status = {data: status}
    end

    # normalize data
    if status[:data].instance_of? Hash
      # recursively normalize the data structure
      status[:data].values.each {|value| normalize(value)}
    elsif not status[:data] and not status[:mtime]
      # default data
      status[:data] = 'missing'
      status[:level] ||= 'danger'
    end

    # normalize time
    # If the called monitor wants to compare status hashes it should store the correct format
    if status[:mtime].instance_of? Time
      status[:mtime] = status[:mtime].gmtime.iso8601
    end

    # normalize level (filling in title when this occurs)
    if status[:level]
      if not LEVELS.include? status[:level]
        status[:title] ||= "invalid status: #{status[:level].inspect}"
        status[:level] = 'fatal'
      end
    else
      if status[:data].instance_of? Hash
        # find the values with the highest status level
        highest = status[:data].
          group_by {|key, value| LEVELS.index(value[:level]) || 9}.max ||
          [9, []]

        # adopt that level
        status[:level] = LEVELS[highest.first] || 'fatal'

        group = highest.last
        if group.length != 1
          # indicate the number of item with that status
          status[:title] = "#{group.length} #{ISSUE_TYPE[status[:level]]}"

          if group.length <= 4
            status[:title] += ': ' + group.map(&:first).join(', ')
          end
        else
          # indicate the item with the problem
          key, value = group.first
          if value[:title]
            status[:title] ||= "#{key} #{value[:title]}"
          else
            status[:title] ||= "#{key} #{value[:data].inspect}"
          end
        end
      else
        # default level
        status[:level] ||= 'success'
      end
    end

    status
  end
end

# load the monitors
Dir[File.expand_path('../monitors/*.rb', __FILE__)].each do |monitor|
  require monitor
end

# for debugging purposes
if __FILE__ == $0
  puts JSON.pretty_generate(StatusMonitor.new(ARGV).status)
end
