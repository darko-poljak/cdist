#!/bin/sh
#
# 2010 Nico Schottelius (nico-cdist at schottelius.org)
#
# This file is part of cdist.
#
# cdist is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# cdist is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with cdist. If not, see <http://www.gnu.org/licenses/>.
#
#
# All os variables are lower case
#
#

cdist_explore_os()
{
   # Ubuntu is also Debian, thus return if Ubuntu was found
   if grep -q ^DISTRIB_ID=Ubuntu /etc/lsb-release 2>/dev/null; then
      echo ubuntu
      return
   fi

   [ -f /etc/arch-release ] && echo archlinux

   [ -f /etc/debian_version ] && echo debian

   [ -f /etc/redhat-release ] && echo redhat

}
