###Last write wins: Swift vs Swift-on-File

**OpenStack Swift:** The timestamp assigned to the request by proxy server
ultimately decides which *last* write wins. A `201 Created` is sent as
response to both the clients. Example:

Transaction T1 at time = t seconds:  
`curl -i http://vm1:8080/v1/AUTH_abc/c1/o1 -X PUT -T /tmp/reallybigfile`  
(Assume it takes 5 seconds to upload the *reallybigfile*)

Transaction T2 at time = (t + 0.01) seconds:  
`curl -i http://vm1:8080/v1/AUTH_abc/c1/o1 -X PUT -d 'tinydata'`  
(Assume it takes 1 second to upload this tiny data)

Here T2 wins although T1 will complete last. This is because T2 was the last
one to reach proxy server (the client facing server process that tags the
request with a timestamp).

Simultaneous PUT and DELETE illustrated: If a client has a long running PUT to
`AUTH_abc/c1/o1` and another client issues a DELETE on `AUTH_abc/c1/o1`
during the ongoing upload:

1. If the object existed earlier, the tombstone(.ts) created by DELETE request
   will have a later timestamp and will eventually take precedence even if the
   other upload finishes after. In effect, to any new clients performing a
   HEAD/GET on `AUTH_abc/c1/o1`, the client would receive a `HTTP 404` response
   as the object stands deleted.
2. If object did not exist earlier, the client doing a DELETE would recieve a
   `HTTP 404` response. The client doing the PUT request will successfully
   upload the object.

**Swift-on-File:** Unlike in vanilla OpenStack Swift, Swift-on-File does not
honour the timestamp set on request by the proxy server to decide which of
the write is the "last" one. In Swift-on-File, the last write to complete
(at the filesystem layer) is the one that wins. Example:

Transaction T1 at time = t seconds:  
`curl -i http://vm1:8080/v1/AUTH_abc/c1/o1 -X PUT -T /tmp/reallybigfile`  
(Assume it takes 5 seconds to upload the *reallybigfile*)

Transaction T2 at time = (t + 0.01) seconds:  
`curl -i http://vm1:8080/v1/AUTH_abc/c1/o1 -X PUT -d 'tinydata'`  
(Assume it takes 1 second to upload this tiny data)

Here T1 wins although T2 is the last transaction among the two to reach the
proxy server. This is because T1 was the last to complete and will overwrite
the object created by T2. For a small duration, between T2 completed and
T1 in progress, clients will be served the object created by T2.

Simultaneous PUT and DELETE illustrated: If a client has a long running PUT to
`AUTH_abc/c1/o1` and another client issues a DELETE on `AUTH_abc/c1/o1` during
the ongoing upload, the DELETE request would be responded with either of these:

* `HTTP 404` as the file does not exist because it's still being uploaded to
   a temp path and rename has not been performed yet.
* `HTTP 204` as an older version of the file existed and the DELETE was
   successful.

In effect, after completion of both PUT and DELETE, to any new client
performing a HEAD/GET on `AUTH_abc/c1/o1`, the client would receive the newer
object uploaded by the last PUT operation.

###Access from fileystem interface

Operations done solely from Swift interface will create/modify the objects
atomically. A PUT would result in data being written to a temporary file and
when the write of data and metadata is complete, the temporary file is renamed
to it's actual name. Hence, any client accessing the file/object from file
interface or Swift interface will see the file in a consistent state (either
the previous version or the newer version).

However, it's different when you create/modify file from filesystem interface.
As the file is written to it's actual path and not some temporary location,
a GET on the file from Swift interface while the file is being written from
filesystem interface might result in the Swift client getting partial file.
In other words, swiftonfile will serve the object present in filesystem
"as is" without checking if the file is being written or not.
