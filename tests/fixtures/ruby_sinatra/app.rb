require 'sinatra'
require_relative 'helpers'

get '/' do
  greeting('world')
end
